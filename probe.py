"""Learn the REAL service. Phase 1: 15 sequential calls (latency spread). Phase 2: bursts until the first 429, then poll until recovery.
Writes probe_raw.csv (results.csv columns) + limits.json (raw headers/429 body for Table 1). Costs ~100 of your daily requests."""
import asyncio, csv, json, time, datetime, httpx, sys
import config as C
P = [{"role": "user", "content": "In two sentences, explain what self-attention is."}]
rows, info = [], dict(headers_sample=None, first_429=None, ok_before_429=0, recover_s=None)

async def one(c, rid, scen):
    t0 = time.perf_counter(); ft = None; n = 0; st = "ok"; h = {}
    try:
        async with c.stream("POST", C.BASE_URL + "/chat/completions", headers={"Authorization": "Bearer " + C.API_KEY},
                            json=dict(model=C.MODEL, messages=P, max_tokens=80, stream=True)) as r:
            h = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
            if r.status_code == 429:
                st = "rate_limited"; b = (await r.aread()).decode()
                if not info["first_429"]: info["first_429"] = dict(body=b[:500], headers=h)
            elif r.status_code != 200: st = "error"; await r.aread()
            else:
                if not info["headers_sample"]: info["headers_sample"] = h
                async for line in r.aiter_lines():
                    if line.startswith("data:") and "[DONE]" not in line and '"content"' in line:
                        if ft is None: ft = (time.perf_counter() - t0) * 1000
                        n += 1
    except Exception: st = "timeout"
    tot = (time.perf_counter() - t0) * 1000
    rows.append(dict(request_id=rid, scenario=scen, source="real", start_time=datetime.datetime.now().isoformat(), first_token_ms=round(ft or 0, 1) if ft else "",
                     total_ms=round(tot, 1), status=st, retries=0, tokens_in="", tokens_out=n, retrieval_setting="none", answer_grade=""))
    return st

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        for i in range(15): await one(c, f"seq{i}", "probe_seq"); await asyncio.sleep(1)
        print("phase 1 done; phase 2 bursts…"); i = 0; t_start = time.time()
        while info["first_429"] is None and i < 90:
            r = await asyncio.gather(*[one(c, f"b{i+j}", "probe_burst") for j in range(5)]); i += 5
            info["ok_before_429"] += r.count("ok"); await asyncio.sleep(0.5)
        if info["first_429"]:
            t429 = time.time()
            while time.time() - t429 < 180:
                await asyncio.sleep(3)
                if await one(c, f"rec{int(time.time())}", "probe_recover") == "ok": info["recover_s"] = round(time.time() - t429, 1); break
        info["burst_window_s"] = round(time.time() - t_start, 1)
    with open("probe_raw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump(info, open("limits.json", "w"), indent=1); print(json.dumps(info, indent=1))
asyncio.run(main())
