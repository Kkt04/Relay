import asyncio, random, re, time
import config as C
from llm import gov, chat, RateLimited, Transient
from retrieval import SETTINGS, get_index, toks

NOT_IN = "NOT_IN_PAPERS"
SYS = ("You answer ONLY from the numbered passages. Cite every claim with [n]. If the passages do not contain the answer, "
       "reply exactly: NOT_IN_PAPERS. Max 4 sentences. Never use outside knowledge.")
REFUSE = "The three papers (Attention Is All You Need, Moshi, Dynamic Chunking) don't say this, so I won't guess."
VFAIL = "I couldn't produce an answer I could verify against the papers, so I won't guess. Try rephrasing the question."
norm = lambda s: " ".join(re.findall(r"[a-z0-9]+", s.lower()))

async def verify_tool(ans, ps):
    """The tool call: checks [n] citations exist and quoted spans really occur in the passages. Can be slow/fail (fault injection)."""
    if random.random() < C.TOOL_SLOW_P: await asyncio.sleep(C.TOOL_SLOW_S)
    if random.random() < C.TOOL_FAIL_P: raise RuntimeError("tool down")
    cites = [int(x) for x in re.findall(r"\[(\d+)\]", ans)]
    if not cites or any(c < 1 or c > len(ps) for c in cites): return False, "bad citation"
    big = norm(" ".join(p["text"] for p in ps))
    for qt in re.findall(r'"([^"]{12,})"', ans):
        if norm(qt) not in big: return False, "quote not in passages"
    return True, ""

def extractive(ps, q, prefix):
    qs, best = set(toks(q)), []
    for i, p in enumerate(ps[:2], 1):
        for s in re.split(r"(?<=[.!?]) ", p["text"]): best.append((len(qs & set(toks(s))), i, " ".join(s.split()[:50])))
    best.sort(key=lambda x: -x[0])
    return prefix + " ".join(f"\u201c{s}\u201d [{i}]" for _, i, s in best[:2])

async def run(q, setting, ctx, emit=None):
    async def em(t, d=None):
        if emit: await emit(t, d)
    async def st(name, state, info=""): await em("stage", dict(name=name, state=state, ms=round((time.monotonic() - ctx.t0) * 1000), info=info))
    def fin(ans, refused, ps, mode):
        if ctx.first_token_ms is None: ctx.first_token_ms = (time.monotonic() - ctx.t0) * 1000
        used = sorted({int(x) for x in re.findall(r"\[(\d+)\]", ans)}) if not refused else []
        cites = [dict(n=n, paper=ps[n-1]["paper"], arxiv=ps[n-1]["arxiv"], page=ps[n-1]["page"]) for n in used if 1 <= n <= len(ps)]
        late = (time.monotonic() - ctx.t0) > ctx.patience
        passages = [dict(n=i+1, paper=p["paper"], arxiv=p["arxiv"], page=p["page"], text=p["text"],
                         score=round(p.get("score", 0), 2), cov=round(p.get("cov", 0), 2)) for i, p in enumerate(ps)]
        return dict(status="timeout" if late else "ok", answer=ans, refused=refused, citations=cites, passages=passages, mode=mode)

    size, k, rr = SETTINGS[setting]; mode = "full"
    if gov.daily_exhausted: mode = "quick"
    elif gov.pressure() >= C.LITE_AT: mode, k, rr = "lite", max(2, k // 2), False
    query = q
    if mode == "full":                                              # 1 understand (LLM call, skipped under pressure)
        await st("understand", "start")
        try:
            kw = await chat(ctx, [{"role": "user", "content": "###TASK:understand\nGive 6-10 search keywords (no sentence) for finding the answer to this question in research papers:\n" + q}], max_tokens=30)
            query = q + " " + kw
        except RateLimited as e: mode = "quick" if e.daily else "lite"
        except Transient: mode = "lite"
        await st("understand", "done")
    else: await st("understand", "skip")
    await st("retrieve", "start")                                   # 2 retrieve
    ps = get_index(size).search(query, k, rr, cov_q=q)
    await st("retrieve", "done", f"{len(ps)} passages")
    await st("decide", "start")                                     # 3 branch: answerable at all?
    if not ps or ps[0]["cov"] < C.REFUSE_COV:
        await st("decide", "done", "not in papers"); await st("draft", "skip"); await st("verify", "skip")
        return fin(REFUSE, True, ps, mode)
    await st("decide", "done", mode)
    if mode == "quick":
        await st("draft", "skip"); await st("verify", "skip")
        pre = "Today's AI quota is used up, so this is a quick answer taken straight from the papers (full answers return after reset): " if gov.daily_exhausted else "We're very busy, so this is a quick answer taken straight from the papers: "
        return fin(extractive(ps, q, pre), False, ps, "quick")
    ctxt = "\n".join(f"[{i+1}] ({p['paper']}, p.{p['page']}): {p['text']}" for i, p in enumerate(ps))
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": f"###TASK:draft\nPassages:\n{ctxt}\n\nQuestion: {q}"}]
    buf, sent = "", 0
    async def on_tok(t):                                            # stream draft, but hold back a possible "NOT_IN_PAPERS"
        nonlocal buf, sent
        if t is None: buf, sent = "", 0; await em("replace", ""); return
        buf += t
        if NOT_IN.startswith(buf.strip()): return
        if ctx.first_token_ms is None: ctx.first_token_ms = (time.monotonic() - ctx.t0) * 1000
        await em("token", buf[sent:]); sent = len(buf)
    for attempt in range(2):                                        # 4+5 draft -> verify -> (loop once)
        buf, sent = "", 0
        if attempt: await em("replace", "")
        await st("draft", "start")
        try: ans = (await chat(ctx, msgs, 200 if mode == "lite" else 300, True, on_tok)).strip()
        except (RateLimited, Transient):
            await st("draft", "done", "busy"); await st("verify", "skip")
            return fin(extractive(ps, q, "We're very busy, so this is a quick answer taken straight from the papers: "), False, ps, "quick")
        await st("draft", "done")
        if ans.startswith(NOT_IN): await st("verify", "skip"); return fin(REFUSE, True, ps, mode)
        await st("verify", "start")
        try: ok, why = await asyncio.wait_for(verify_tool(ans, ps), C.TOOL_TIMEOUT); checked = True
        except Exception: ok, why, checked = True, "", False
        await st("verify", "done", "ok" if ok else why)
        if ok: break
        msgs[-1]["content"] += f"\n\nYour previous answer failed a check ({why}). Cite only [1]-[{len(ps)}] and quote exactly."
    else: return fin(VFAIL, True, ps, mode)
    if not checked: ans += "\n(Note: the automatic citation check was unavailable for this reply.)"
    return fin(ans, False, ps, mode)
