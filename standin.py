"""Stand-in model service (OpenAI/Groq-compatible). Run: uvicorn standin:app --port 9000
Can be slow (lognormal TTFT), fail (5xx), succeed slowly (tail), slow down under load, hit RPM/TPM/RPD/in-flight limits (429 + retry-after), stream token by token."""
import asyncio, collections, json, math, os, random, re, time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
CFG = dict(ttft_mu=math.log(350), ttft_sigma=0.5, tok_ms=6.0, load_slow=0.08, fail_rate=0.0, slow_p=0.02, slow_mult=8.0,
           rpm=30, tpm=6000, rpd=14400, tpd=500000, max_inflight=10)
if os.path.exists("standin_config.json"): CFG.update(json.load(open("standin_config.json")))
S = {}
def reset(): S.update(req=collections.deque(), tok=collections.deque(), rpd=0, tpd=0, inflight=0, day=time.time())
reset()

def make_reply(text, maxt):
    if "###TASK:understand" in text:
        q = text.split("papers:")[-1]; out = ", ".join([w for w in re.findall(r"[A-Za-z0-9\-]+", q) if len(w) > 3][:8])
    else:
        m = re.search(r"\[1\] \([^)]*\): (.+?)(?:\n\[2\]|\n\nQuestion)", text, re.S)
        out = (" ".join(re.split(r"(?<=[.!?]) ", m.group(1).strip())[:2]) + " [1]") if m else "OK"
    return " ".join(out.split()[:max(3, int(maxt / 1.3))])

@app.post("/admin/config")
async def set_cfg(r: Request): CFG.update(await r.json()); return CFG
@app.post("/admin/reset")
async def do_reset(): reset(); return "ok"
@app.get("/admin/state")
async def state(): return dict(cfg=CFG, rpd=S["rpd"], inflight=S["inflight"])

@app.post("/v1/chat/completions")
async def chat(req: Request):
    b = await req.json(); now = time.time()
    text = " ".join(m["content"] for m in b["messages"]); tin = len(text) // 4 + 1; maxt = b.get("max_tokens", 300)
    while S["req"] and now - S["req"][0] > 60: S["req"].popleft()
    while S["tok"] and now - S["tok"][0][0] > 60: S["tok"].popleft()
    used = sum(t for _, t in S["tok"]); why = retry = None
    if S["rpd"] >= CFG["rpd"]: why, retry = "requests per day (RPD)", max(1, 86400 - (now - S["day"]))
    elif S["tpd"] >= CFG["tpd"]: why, retry = "tokens per day (TPD)", max(1, 86400 - (now - S["day"]))
    elif len(S["req"]) >= CFG["rpm"]: why, retry = "requests per minute (RPM)", 60 - (now - S["req"][0])
    elif used + tin + maxt > CFG["tpm"]: why, retry = "tokens per minute (TPM)", 60 - (S["tok"][0][0] and now - S["tok"][0][0]) if S["tok"] else 1
    elif S["inflight"] >= CFG["max_inflight"]: why, retry = "concurrency", 1
    hdr = {"x-ratelimit-limit-requests": str(CFG["rpd"]), "x-ratelimit-remaining-requests": str(max(0, CFG["rpd"] - S["rpd"])),
           "x-ratelimit-limit-tokens": str(CFG["tpm"]), "x-ratelimit-remaining-tokens": str(max(0, CFG["tpm"] - used))}
    if why:
        hdr["retry-after"] = str(math.ceil(retry))
        return JSONResponse({"error": {"message": f"Rate limit reached on {why}. Please try again in {retry:.1f}s.", "type": "rate_limit_exceeded"}}, 429, hdr)
    S["req"].append(now); S["tok"].append((now, tin + maxt)); S["rpd"] += 1; S["tpd"] += tin
    if random.random() < CFG["fail_rate"]:
        await asyncio.sleep(0.2); return JSONResponse({"error": {"message": "internal error"}}, 503, hdr)
    reply = make_reply(text, maxt); words = reply.split(); S["inflight"] += 1
    slow = (1 + CFG["load_slow"] * S["inflight"]) * (CFG["slow_mult"] if random.random() < CFG["slow_p"] else 1)
    ttft = random.lognormvariate(CFG["ttft_mu"], CFG["ttft_sigma"]) / 1000 * slow; per = CFG["tok_ms"] * 1.3 / 1000 * slow
    usage = dict(prompt_tokens=tin, completion_tokens=int(len(words) * 1.3) + 1)
    if not b.get("stream"):
        try: await asyncio.sleep(ttft + per * len(words))
        finally: S["inflight"] -= 1
        return JSONResponse({"choices": [{"message": {"role": "assistant", "content": reply}}], "usage": usage}, headers=hdr)
    async def gen():
        try:
            await asyncio.sleep(ttft)
            for i, w in enumerate(words):
                yield "data: " + json.dumps({"choices": [{"delta": {"content": ("" if i == 0 else " ") + w}}]}) + "\n\n"; await asyncio.sleep(per)
            yield "data: " + json.dumps({"choices": [], "x_groq": {"usage": usage}}) + "\n\ndata: [DONE]\n\n"
        finally: S["inflight"] -= 1
    return StreamingResponse(gen(), media_type="text/event-stream", headers=hdr)
