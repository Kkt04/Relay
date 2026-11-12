import os
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
API_KEY = os.getenv("GROQ_API_KEY", "none")
MODEL = os.getenv("MODEL", "llama-3.1-8b-instant")   # check Groq docs for current free-tier model names
SOURCE = "stand-in" if ("127.0.0.1" in BASE_URL or "localhost" in BASE_URL) else "real"
f = lambda k, d: type(d)(os.getenv(k, d))
# --- limits we believe exist (overwrite from your Table 1 via env vars) ---
RPM, TPM, RPD = f("RPM", 30), f("TPM", 6000), f("RPD", 14400)
SAFETY = f("SAFETY", 0.9)          # stay at 90% of the limit
# --- policy knobs (every one of these is a decision you must defend) ---
MAX_INFLIGHT = f("MAX_INFLIGHT", 6)
MAX_QUEUE = f("MAX_QUEUE", 60)     # beyond this, shed to quick answer
PATIENCE = f("PATIENCE", 20.0)     # seconds before the person gives up
WAIT_BUDGET = f("WAIT_BUDGET", 6.0)  # max seconds one call may queue at our limiter before we degrade
GRACE = f("GRACE", 2.0)            # stop waiting this long before patience ends
MAX_RETRIES = f("MAX_RETRIES", 3)
BACKOFF_BASE, BACKOFF_CAP = f("BACKOFF_BASE", 1.0), f("BACKOFF_CAP", 15.0)
CALL_TIMEOUT = f("CALL_TIMEOUT", 15.0)
LITE_AT = f("LITE_AT", 0.7)        # load level where we switch to fast mode
REFUSE_COV = f("REFUSE_COV", 0.35) # min share of question words found in best passage
TOOL_TIMEOUT = f("TOOL_TIMEOUT", 1.0)
TOOL_FAIL_P, TOOL_SLOW_P, TOOL_SLOW_S = f("TOOL_FAIL_P", 0.0), f("TOOL_SLOW_P", 0.0), f("TOOL_SLOW_S", 3.0)
PRICE_IN, PRICE_OUT = f("PRICE_IN", 0.05), f("PRICE_OUT", 0.08)  # USD per 1M tokens, verify on Groq pricing page
