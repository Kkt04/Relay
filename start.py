"""One command for the demo: python3 start.py
Open http://localhost:8000
"""
import os, subprocess, sys, time

# 1. Load environment variables from .env if it exists
def load_dotenv():
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key not in os.environ:
                        os.environ[key] = val

load_dotenv()

env = dict(os.environ)
ps = []

# 2. Check if a real Groq API key is configured
groq_key = env.get("GROQ_API_KEY", "").strip()
if not groq_key or groq_key == "none":
    env["LLM_BASE_URL"] = "http://127.0.0.1:9000/v1"
    print("\nℹ️  No GROQ_API_KEY detected in .env or environment.")
    print("👉 Starting local calibrated stand-in model on port 9000...")
    ps.append(subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "standin:app", "--port", "9000", "--log-level", "warning"],
        env=env
    ))
    time.sleep(1.5)
else:
    print(f"\n🔑 GROQ_API_KEY detected ({groq_key[:6]}...{groq_key[-4:]})")
    print("🚀 Connecting directly to real Groq cloud service!")

print("🌐 Starting Web UI on http://localhost:8000 ...")
print("Press Ctrl+C to stop the server anytime.\n")

try:
    subprocess.run([sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"], env=env)
except KeyboardInterrupt:
    print("\n👋 Server stopped gracefully.")
finally:
    for p in ps:
        p.terminate()
