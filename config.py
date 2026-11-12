import os

# Automatically load .env if present
def _load_env():
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    if k not in os.environ:
                        os.environ[k] = v

_load_env()

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
API_KEY = os.getenv("GROQ_API_KEY", "none")
MODEL = os.getenv("MODEL", "llama-3.1-8b-instant")
SOURCE = "stand-in" if ("127.0.0.1" in BASE_URL or "localhost" in BASE_URL or API_KEY == "none" or not API_KEY) else "real"

f = lambda k, d: type(d)(os.getenv(k, d))
# --- limits we believe exist (overwrite from your Table 1 via env vars) ---
RPM, TPM, RPD = f("RPM", 30), f("TPM", 20000), f("RPD", 14400)
SAFETY = f("SAFETY", 0.9)          # stay at 90% of the limit

# --- policy knobs (every one of these is a decision you must defend) ---
MAX_INFLIGHT = f("MAX_INFLIGHT", 6)
MAX_QUEUE = f("MAX_QUEUE", 60)     # beyond this, shed to quick answer
PATIENCE = f("PATIENCE", 20.0)     # seconds before the person gives up
WAIT_BUDGET = f("WAIT_BUDGET", 1.8)  # max seconds one call may queue at our limiter before we degrade
GRACE = f("GRACE", 1.5)            # stop waiting this long before patience ends
MAX_RETRIES = f("MAX_RETRIES", 2)
BACKOFF_BASE, BACKOFF_CAP = f("BACKOFF_BASE", 0.8), f("BACKOFF_CAP", 5.0)
CALL_TIMEOUT = f("CALL_TIMEOUT", 15.0)
LITE_AT = f("LITE_AT", 0.7)        # load level where we switch to fast mode
REFUSE_COV = f("REFUSE_COV", 0.35) # min share of question words found in best passage
TOOL_TIMEOUT = f("TOOL_TIMEOUT", 1.0)
TOOL_FAIL_P, TOOL_SLOW_P, TOOL_SLOW_S = f("TOOL_FAIL_P", 0.0), f("TOOL_SLOW_P", 0.0), f("TOOL_SLOW_S", 3.0)
PRICE_IN, PRICE_OUT = f("PRICE_IN", 0.05), f("PRICE_OUT", 0.08)  # USD per 1M tokens
