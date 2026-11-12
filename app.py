import asyncio, json, time
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
import config as C
from llm import Ctx, gov
from pipeline import run
app = FastAPI()

@app.get("/")
async def home(): return FileResponse("web/index.html")
@app.get("/status")
async def status(): return gov.stats()
@app.get("/ask")
async def ask(q: str, setting: str = "S2_200w_k4"):
    box = asyncio.Queue(); ctx = Ctx(C.PATIENCE)
    async def emit(t, d): await box.put((t, d))
    async def work():
        try: r = await run(q, setting, ctx, emit)
        except Exception as e: r = dict(status="error", answer="Something went wrong. Please try again.", citations=[], mode="quick")
        r.update(first_token_ms=ctx.first_token_ms or 0, total_ms=(time.monotonic() - ctx.t0) * 1000, retries=ctx.retries)
        await box.put(("final", r)); await box.put(None)
    asyncio.create_task(work())
    async def gen():
        while (it := await box.get()) is not None: yield "data: " + json.dumps({"t": it[0], "d": it[1]}) + "\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
