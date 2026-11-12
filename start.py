"""One command for the demo: python start.py  (no GROQ_API_KEY set -> starts the stand-in automatically). Open http://localhost:8000"""
import os, subprocess, sys, time
env = dict(os.environ); ps = []
if not env.get("GROQ_API_KEY"):
    env["LLM_BASE_URL"] = "http://127.0.0.1:9000/v1"; print("No GROQ_API_KEY -> using the built-in stand-in model.")
    ps.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "standin:app", "--port", "9000", "--log-level", "warning"], env=env)); time.sleep(1.5)
try: subprocess.run([sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"], env=env)
finally: [p.terminate() for p in ps]
