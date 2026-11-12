"""python loadtest.py --scenario steady|burst|overload|rpm_halved|daily_exhausted|retrieval [--setting S2_200w_k4] [--n N]
Stand-in scenarios auto-configure the stand-in (must be running on :9000 with LLM_BASE_URL pointing to it). Appends rows to results.csv."""
import argparse, asyncio, csv, datetime, json, os, random, time, httpx
import config as C
from llm import Ctx, gov
from pipeline import run
from retrieval import SETTINGS

SC = {"steady": dict(n=40, rate=10), "burst": dict(n=100, rate=None), "overload": dict(n=300, rate=900),
      "rpm_halved": dict(n=40, rate=10, cfg=dict(rpm=C.RPM // 2)), "daily_exhausted": dict(n=80, rate=120, cfg=dict(rpd=40))}
COLS = "request_id,scenario,source,start_time,first_token_ms,total_ms,status,retries,tokens_in,tokens_out,retrieval_setting,answer_grade,mode,wait_ms,work_ms,retry_ms,queue_len,question_id".split(",")

def grade(q, r):
    if r["refused"]: return "refused_correctly" if not q["answerable"] else "refused_wrongly"
    if not q["answerable"]: return "wrong"
    ok = any(k.lower() in r["answer"].lower() for k in q["must_any"]) and (not q.get("paper") or q["paper"] in [c["arxiv"] for c in r["citations"]])
    return "correct" if ok else "wrong"

async def one(rid, scen, q, setting, patience):
    ctx = Ctx(patience); st = datetime.datetime.now().isoformat(); r = None
    try: r = await asyncio.wait_for(run(q["q"], setting, ctx), patience + 10); status = r["status"]
    except Exception as e: status = "error"; print("error", repr(e)[:100])
    tot = (time.monotonic() - ctx.t0) * 1000
    return dict(request_id=rid, scenario=scen, source=C.SOURCE, start_time=st, first_token_ms=round(ctx.first_token_ms, 1) if ctx.first_token_ms else "",
                total_ms=round(tot, 1), status=status, retries=ctx.retries, tokens_in=ctx.tin, tokens_out=ctx.tout, retrieval_setting=setting,
                answer_grade=grade(q, r) if r and status == "ok" else "", mode=r["mode"] if r else "", wait_ms=round(ctx.wait), work_ms=round(ctx.work),
                retry_ms=round(ctx.retry), queue_len=ctx.queue_len, question_id=q["id"])

def prep_standin(extra):
    if C.SOURCE != "stand-in": return
    base = C.BASE_URL.rsplit("/v1", 1)[0]; cfg = json.load(open("standin_config.json")) if os.path.exists("standin_config.json") else {}
    cfg.update(dict(rpm=C.RPM, tpm=C.TPM, rpd=C.RPD)); cfg.update(extra or {})
    httpx.post(base + "/admin/reset"); httpx.post(base + "/admin/config", json=cfg)

async def scenario(name, n, rate, setting, patience, out, qs):
    gov.reset(); tasks = []; t0 = time.monotonic(); gap = 60 / rate if rate else 3 / n
    for i in range(n):
        tasks.append(asyncio.create_task(one(f"{name}-{i}", name, qs[i % len(qs)], setting, patience)))
        await asyncio.sleep(max(0, t0 + (i + 1) * gap - time.monotonic()))
    rows = await asyncio.gather(*tasks); new = not os.path.exists(out)
    with open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); new and w.writeheader(); w.writerows(rows)
    ok = sum(r["status"] == "ok" for r in rows); print(f"{name}: {len(rows)} sent, {ok} ok, peak queue {gov.peak}, {time.monotonic()-t0:.0f}s")

async def main():
    a = argparse.ArgumentParser(); a.add_argument("--scenario", required=True); a.add_argument("--setting", default="S2_200w_k4")
    a.add_argument("--n", type=int); a.add_argument("--patience", type=float, default=C.PATIENCE); a.add_argument("--out", default="results.csv"); a = a.parse_args()
    qs = json.load(open("questions.json")); random.seed(1)
    if a.scenario == "retrieval":                      # Table 3: every question once per setting, gentle rate, real service
        for s in SETTINGS:
            prep_standin(None); await scenario(f"retrieval_{s}", len(qs), 12, s, a.patience, a.out, qs)
        return
    sc = SC[a.scenario]; prep_standin(sc.get("cfg"))
    if C.SOURCE == "real" and a.scenario != "steady": print("WARNING: this will hammer your REAL free-tier quota; use the stand-in.")
    random.shuffle(qs); await scenario(a.scenario, a.n or sc["n"], sc["rate"], a.setting, a.patience, a.out, qs)
asyncio.run(main())
