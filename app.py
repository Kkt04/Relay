import asyncio, json, os, time, zipfile, io
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse, Response
import config as C
from llm import Ctx, gov
from pipeline import run

app = FastAPI(title="The Relay", description="Research Assistant with Resilient Pipeline")

@app.get("/")
async def home():
    return FileResponse("web/index.html")

@app.get("/status")
async def status():
    st = gov.stats()
    st.update(
        rpm=C.RPM,
        tpm=C.TPM,
        rpd=C.RPD,
        model=C.MODEL,
        lite_at=C.LITE_AT,
        max_inflight=C.MAX_INFLIGHT,
        max_queue=C.MAX_QUEUE,
        patience=C.PATIENCE
    )
    return st

@app.get("/questions")
async def questions():
    if os.path.exists("questions.json"):
        with open("questions.json") as f:
            return json.load(f)
    return []

@app.post("/toggle-daily")
async def toggle_daily():
    if gov.daily_exhausted:
        gov.daily_until = 0.0
    else:
        gov.daily_until = time.time() + 86400
    return {"daily_exhausted": gov.daily_exhausted}

@app.post("/reset-governor")
async def reset_governor():
    gov.reset()
    return {"status": "ok", "stats": gov.stats()}

@app.get("/ask")
async def ask(q: str, setting: str = "S2_200w_k4"):
    box = asyncio.Queue()
    ctx = Ctx(C.PATIENCE)

    async def emit(t, d):
        await box.put((t, d))

    async def work():
        try:
            r = await run(q, setting, ctx, emit)
        except Exception as e:
            r = dict(
                status="error",
                answer=f"Pipeline error: {str(e)}. Falling back to safe response.",
                citations=[],
                passages=[],
                mode="quick"
            )
        total_ms = (time.monotonic() - ctx.t0) * 1000
        cost = (ctx.tin * C.PRICE_IN + ctx.tout * C.PRICE_OUT) / 1_000_000
        r.update(
            first_token_ms=round(ctx.first_token_ms or 0, 1),
            total_ms=round(total_ms, 1),
            retries=ctx.retries,
            wait_ms=round(ctx.wait, 1),
            work_ms=round(ctx.work, 1),
            retry_ms=round(ctx.retry, 1),
            tokens_in=ctx.tin,
            tokens_out=ctx.tout,
            cost_usd=round(cost, 6),
            queue_len=ctx.queue_len
        )
        await box.put(("final", r))
        await box.put(None)

    asyncio.create_task(work())

    async def gen():
        while (it := await box.get()) is not None:
            yield f"data: {json.dumps({'t': it[0], 'd': it[1]})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/experiments")
async def get_experiments():
    import csv, collections, math
    if not os.path.exists("results.csv"):
        return {"scenarios": {}, "retrieval": {}}
    groups = collections.defaultdict(list)
    with open("results.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            groups[r["scenario"]].append(r)
    
    def pct(v, p):
        v = sorted(v)
        return round(v[min(len(v) - 1, math.ceil(p / 100 * len(v)) - 1)]) if v else None

    scenarios = {}
    for s, s_rows in groups.items():
        if s.startswith(("retrieval_", "probe")): continue
        ft = [float(r["first_token_ms"]) for r in s_rows if r.get("first_token_ms")]
        tot = [float(r["total_ms"]) for r in s_rows if r.get("total_ms")]
        tin = sum(float(r.get("tokens_in") or 0) for r in s_rows) / max(len(s_rows), 1)
        tout = sum(float(r.get("tokens_out") or 0) for r in s_rows) / max(len(s_rows), 1)
        scenarios[s] = {
            "source": s_rows[0]["source"],
            "sent": len(s_rows),
            "succeeded_pct": round(100 * sum(r["status"] == "ok" for r in s_rows) / len(s_rows), 1),
            "rate_limited_pct": round(100 * sum(r["status"] == "rate_limited" for r in s_rows) / len(s_rows), 1),
            "timeout_pct": round(100 * sum(r["status"] == "timeout" for r in s_rows) / len(s_rows), 1),
            "retries_per_req": round(sum(int(r.get("retries") or 0) for r in s_rows) / len(s_rows), 2),
            "peak_queue": max(int(r.get("queue_len") or 0) for r in s_rows),
            "ft_p50": pct(ft, 50),
            "ft_p95": pct(ft, 95),
            "tot_p50": pct(tot, 50),
            "tot_p95": pct(tot, 95),
            "tokens_per_ans": round(tin + tout)
        }

    retrieval = {}
    for s, s_rows in groups.items():
        if not s.startswith("retrieval_"): continue
        name = s[10:]
        ft = [float(r["first_token_ms"]) for r in s_rows if r.get("first_token_ms")]
        tot = [float(r["total_ms"]) for r in s_rows if r.get("total_ms")]
        tin = sum(float(r.get("tokens_in") or 0) for r in s_rows) / max(len(s_rows), 1)
        tout = sum(float(r.get("tokens_out") or 0) for r in s_rows) / max(len(s_rows), 1)
        retrieval[name] = {
            "asked": len(s_rows),
            "correct_pct": round(100 * sum(r.get("answer_grade") == "correct" for r in s_rows) / len(s_rows), 1),
            "wrong_pct": round(100 * sum(r.get("answer_grade") == "wrong" for r in s_rows) / len(s_rows), 1),
            "refused_pct": round(100 * sum(r.get("answer_grade") == "refused_correctly" for r in s_rows) / len(s_rows), 1),
            "tokens": round(tin + tout),
            "ft_p50": pct(ft, 50),
            "ft_p95": pct(ft, 95),
            "tot_p50": pct(tot, 50),
            "tot_p95": pct(tot, 95)
        }
    return {"scenarios": scenarios, "retrieval": retrieval}

@app.get("/download-zip")
async def download_zip():
    zip_path = "relay_submission.zip"
    build_submission_zip(zip_path)
    return FileResponse(zip_path, filename="relay_submission.zip", media_type="application/zip")

def build_submission_zip(out_path="relay_submission.zip"):
    ignore_dirs = {".git", "__pycache__", ".vscode", ".idea"}
    ignore_exts = {".pyc", ".DS_Store"}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for file in files:
                if any(file.endswith(ext) for ext in ignore_exts):
                    continue
                if file == out_path or file == "relay_submission.zip":
                    continue
                if file == ".env" or (file.startswith(".env.") and file != ".env.example"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, ".")
                zf.write(file_path, rel_path)
