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
