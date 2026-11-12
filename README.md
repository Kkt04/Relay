# The Relay (Vaani assignment)

Chain: **understand → retrieve → decide (branch) → draft (streamed) → verify (tool, loop once)**, behind a limiter that degrades gracefully
(full answer → fast mode → quick extractive answer from the papers) instead of turning people away.

## Quick demo (animated UI, no key needed)
```
pip install -r requirements.txt
python fetch_papers.py          # downloads the 3 papers at exact versions
python start.py                 # open http://localhost:8000
```
No `GROQ_API_KEY` set -> a built-in stand-in model runs automatically. With a key: `set GROQ_API_KEY=...` (Windows) / `export GROQ_API_KEY=...` (Mac/Linux), then `python start.py`.

## Assignment workflow
1. `python probe.py` (real Groq) -> `probe_raw.csv`, `limits.json` -> fill **Table 1** (set RPM/TPM/RPD env vars from it).
2. `python calibrate.py` -> `standin_config.json` (stand-in copies your measured latency; `load_slow` is assumed, say so).
3. `python -m uvicorn standin:app --port 9000` in terminal 1; in terminal 2 `set LLM_BASE_URL=http://127.0.0.1:9000/v1`.
4. `python loadtest.py --scenario steady|burst|overload|rpm_halved|daily_exhausted` (stand-in). Run one `steady` for real too (unset LLM_BASE_URL).
5. `python loadtest.py --scenario retrieval` (real, 4 settings x all questions) -> Table 3.
6. `python report.py results.csv` -> Tables 2a/2b/3. Merge `probe_raw.csv` rows into `results.csv` if you want probe data included.

## Must be YOURS before submitting
- Write **15+ own questions** in `questions.json` (8 starters are only a template: verify each answer in the PDF; add `must_any` keywords).
- Verify my assumptions: Groq free limits and model name (docs + `limits.json`), prices in `config.py`, whether Groq counts `max_tokens` toward TPM.
- The 2-page write-up, Vaani feedback, and your real chat history. Tune `REFUSE_COV`, `LITE_AT`, `PATIENCE` from your own numbers and be ready to change them live.
- Extra CSV columns (mode, wait/work/retry ms, queue_len, question_id) are appended after the required ones; section 4 (waiting/working/retrying) comes from them.
- Hints for "misleads a naive retriever" (verify yourself): references pages, PDF text extraction breaking tables/equations, the word "attention" appearing in all papers, chunks splitting a number from its label.
# Relay
