import asyncio, json, random, time, httpx
import config as C

class RateLimited(Exception):
    def __init__(s, msg, daily=False, ra=0.0): super().__init__(msg); s.daily, s.ra = daily, ra
class Transient(Exception): pass

class Governor:
    """Client-side limiter: sliding-window RPM/TPM, concurrency cap, queue cap, learns from 429s (AIMD)."""
    def __init__(s): s.reset()
    def reset(s):
        s.req, s.tok, s.queued, s.peak, s.scale, s.streak, s.daily_until = [], [], 0, 0, 1.0, 0, 0.0
        s.sem = asyncio.Semaphore(C.MAX_INFLIGHT)
    @property
    def daily_exhausted(s): return time.time() < s.daily_until
    def _trim(s):
        n = time.monotonic(); s.req = [t for t in s.req if n - t < 60]; s.tok = [(t, x) for t, x in s.tok if n - t < 60]
    def pressure(s):
        s._trim(); cap = s.scale * C.SAFETY
        return min(1.0, max(len(s.req) / (C.RPM * cap), sum(x for _, x in s.tok) / (C.TPM * cap), s.queued / C.MAX_QUEUE))
    async def acquire(s, tokens, ctx):
        t0 = time.monotonic(); lim = min(ctx.deadline - C.GRACE, t0 + C.WAIT_BUDGET)
        if s.queued >= C.MAX_QUEUE: raise RateLimited("queue full")
        s.queued += 1; s.peak = max(s.peak, s.queued); got = False
        try:
            await asyncio.wait_for(s.sem.acquire(), max(0.01, lim - time.monotonic())); got = True
            while True:
                s._trim(); n = time.monotonic(); cap = s.scale * C.SAFETY
                if len(s.req) < int(C.RPM * cap) and sum(x for _, x in s.tok) + tokens <= C.TPM * cap: break
                if n > lim: raise RateLimited("waited too long")
                oldest = min([t for t in s.req] + [t for t, _ in s.tok] or [n])
                await asyncio.sleep(min(1.0, max(0.05, oldest + 60 - n)))
            s.req.append(time.monotonic()); s.tok.append((time.monotonic(), tokens))
        except asyncio.TimeoutError: raise RateLimited("would exceed patience")
        except BaseException:
            if got: s.sem.release()
            raise
        finally: s.queued -= 1; ctx.wait += (time.monotonic() - t0) * 1000
    def release(s): s.sem.release()
    def on_429(s, body, ra):
        low = body.lower()
        if "per day" in low or "(rpd)" in low or "(tpd)" in low: s.daily_until = time.time() + ra; return True
        s.scale = max(0.2, s.scale * 0.7); s.streak = 0; return False
    def on_ok(s):
        s.streak += 1
        if s.streak >= 10 and s.scale < 1: s.scale = min(1.0, s.scale * 1.1); s.streak = 0
    def stats(s):
        return dict(pressure=round(s.pressure(), 2), queued=s.queued, peak=s.peak, scale=round(s.scale, 2), daily=s.daily_exhausted, source=C.SOURCE)

gov = Governor()

class Ctx:
    """Per-request ledger: wait (queued at our limiter) / work (calls that succeeded) / retry (failed attempts + backoff)."""
    def __init__(s, patience=None):
        s.patience = patience or C.PATIENCE; s.t0 = time.monotonic(); s.deadline = s.t0 + s.patience
        s.wait = s.work = s.retry = 0.0; s.retries = s.tin = s.tout = 0; s.first_token_ms = None; s.queue_len = gov.queued

_client = None
def client():
    global _client
    if _client is None: _client = httpx.AsyncClient(timeout=httpx.Timeout(C.CALL_TIMEOUT, connect=5), limits=httpx.Limits(max_connections=400))
    return _client

async def _call(ctx, messages, max_tokens, stream, on_token):
    body = dict(model=C.MODEL, messages=messages, max_tokens=max_tokens, temperature=0.1, stream=stream)
    out, usage = [], None
    async with client().stream("POST", C.BASE_URL + "/chat/completions", headers={"Authorization": "Bearer " + C.API_KEY}, json=body) as r:
        if r.status_code == 429:
            b = (await r.aread()).decode(errors="ignore")
            try: ra = float(r.headers.get("retry-after") or 5)
            except ValueError: ra = 5.0
            raise RateLimited(b[:150], gov.on_429(b, ra), ra)
        if r.status_code >= 500: await r.aread(); raise Transient(str(r.status_code))
        if r.status_code != 200: raise RuntimeError(f"{r.status_code} {(await r.aread())[:200]!r}")
        if not stream:
            j = json.loads(await r.aread()); out.append(j["choices"][0]["message"]["content"]); usage = j.get("usage")
        else:
            async for line in r.aiter_lines():
                if not line.startswith("data:"): continue
                d = line[5:].strip()
                if d == "[DONE]": break
                j = json.loads(d); usage = (j.get("x_groq") or {}).get("usage") or j.get("usage") or usage
                if j.get("choices"):
                    t = j["choices"][0]["delta"].get("content")
                    if t:
                        out.append(t)
                        if on_token: await on_token(t)
    text = "".join(out)
    ctx.tin += (usage or {}).get("prompt_tokens") or len(json.dumps(messages)) // 4
    ctx.tout += (usage or {}).get("completion_tokens") or len(text) // 4
    return text

async def chat(ctx, messages, max_tokens=300, stream=False, on_token=None):
    est = len(json.dumps(messages)) // 4 + 1 + max_tokens
    for attempt in range(C.MAX_RETRIES + 1):
        if time.monotonic() > ctx.deadline - C.GRACE: raise RateLimited("out of patience")
        await gov.acquire(est, ctx); t = time.monotonic()
        try:
            try: text = await asyncio.wait_for(_call(ctx, messages, max_tokens, stream, on_token), ctx.deadline - time.monotonic())
            finally: gov.release()
            ctx.work += (time.monotonic() - t) * 1000; gov.on_ok(); return text
        except RateLimited as e:
            ctx.retry += (time.monotonic() - t) * 1000
            # never wait for a Retry-After that outlasts the person's patience, degrade instead
            if e.daily or attempt == C.MAX_RETRIES or e.ra > ctx.deadline - time.monotonic() - C.GRACE: raise
            delay = max(e.ra, C.BACKOFF_BASE * 2 ** attempt)
        except (Transient, asyncio.TimeoutError, httpx.HTTPError):
            ctx.retry += (time.monotonic() - t) * 1000
            if attempt == C.MAX_RETRIES: raise Transient("gave up")
            delay = C.BACKOFF_BASE * 2 ** attempt
        ctx.retries += 1
        if on_token: await on_token(None)           # tell the UI to discard a half-streamed draft
        delay = min(C.BACKOFF_CAP, delay) * random.uniform(0.8, 1.2)
        ctx.retry += delay * 1000; await asyncio.sleep(delay)
