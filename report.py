"""results.csv -> Markdown for Tables 2a, 2b, 3 (all numbers recomputable from the CSV)."""
import csv, math, sys, datetime, collections
import config as C
R = list(csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 else "results.csv"))); G = collections.defaultdict(list)
for r in R: G[r["scenario"]].append(r)
def pct(v, p):
    v = sorted(v); return round(v[min(len(v) - 1, math.ceil(p / 100 * len(v)) - 1)]) if v else "n/a"
def trio(v): return " / ".join(str(pct(v, p)) for p in (50, 95, 99))
num = lambda rows, k: [float(r[k]) for r in rows if r[k] not in ("", None)]
ts = lambda r: datetime.datetime.fromisoformat(r["start_time"]).timestamp()
print("### Table 2a\n| Scenario | Real/stand-in | Sent | Duration s | Offered/min | First token p50/p95/p99 ms | Total p50/p95/p99 ms |\n|---|---|---|---|---|---|---|")
for s, rows in G.items():
    if s.startswith(("retrieval_", "probe")): continue
    st = [ts(r) for r in rows]; dur = max(t + float(r["total_ms"]) / 1000 for t, r in zip(st, rows)) - min(st); span = max(max(st) - min(st), 1)
    print(f"| {s} | {rows[0]['source']} | {len(rows)} | {dur:.1f} | {len(rows)/span*60:.0f} | {trio(num(rows,'first_token_ms'))} | {trio(num(rows,'total_ms'))} |")
print("\n### Table 2b\n| Scenario | Succeeded % | Rate-limited % | Timed out % | Retries/req | Peak queue | Tokens/answer | Cost per 1000 answers (USD, list price) |\n|---|---|---|---|---|---|---|---|")
for s, rows in G.items():
    if s.startswith(("retrieval_", "probe")): continue
    n = len(rows); p = lambda k: f"{100*sum(r['status']==k for r in rows)/n:.1f}"
    ti = sum(float(r["tokens_in"] or 0) for r in rows) / n; to = sum(float(r["tokens_out"] or 0) for r in rows) / n
    print(f"| {s} | {p('ok')} | {p('rate_limited')} | {p('timeout')} | {sum(int(r['retries']) for r in rows)/n:.2f} | {max(int(r['queue_len'] or 0) for r in rows)} | {ti+to:.0f} ({ti:.0f} in/{to:.0f} out) | {(ti*C.PRICE_IN+to*C.PRICE_OUT)/1000:.4f} |")
print("\n### Table 3\n| Setting | Asked | Correct+cited % | Wrong % | Correctly refused % | Tokens/answer | First token p50/p95 ms | Total p50/p95 ms |\n|---|---|---|---|---|---|---|---|")
for s, rows in G.items():
    if not s.startswith("retrieval_"): continue
    n = len(rows); g = lambda k: f"{100*sum(r['answer_grade']==k for r in rows)/n:.1f}"
    tk = sum(float(r["tokens_in"] or 0) + float(r["tokens_out"] or 0) for r in rows) / n; f, t = num(rows, "first_token_ms"), num(rows, "total_ms")
    print(f"| {s[10:]} | {n} | {g('correct')} | {g('wrong')} | {g('refused_correctly')} | {tk:.0f} | {pct(f,50)} / {pct(f,95)} | {pct(t,50)} / {pct(t,95)} |")
