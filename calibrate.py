"""probe_raw.csv (real) -> standin_config.json. load_slow is NOT fitted (assumed): say so in section 2."""
import csv, json, math, statistics as st
R = [r for r in csv.DictReader(open("probe_raw.csv")) if r["status"] == "ok" and r["scenario"] == "probe_seq" and r["first_token_ms"]]
assert len(R) >= 5, "need >=5 ok sequential rows"
ft = [float(r["first_token_ms"]) for r in R]; tot = [float(r["total_ms"]) for r in R]; n = [max(1, int(r["tokens_out"])) for r in R]
lg = [math.log(x) for x in ft]; med = st.median(ft)
cfg = dict(ttft_mu=st.mean(lg), ttft_sigma=max(0.1, st.pstdev(lg)), tok_ms=max(0.5, st.median([(t - f) / k for t, f, k in zip(tot, ft, n)])),
           slow_p=sum(x > 3 * med for x in ft) / len(ft))
json.dump(cfg, open("standin_config.json", "w"), indent=1); print(cfg)
