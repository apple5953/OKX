import os
import runpy
import sys

ROOT = r"D:\okx\harmonic_agent"
LOG_OUT = os.path.join(ROOT, "scratch", "server.out.log")
LOG_ERR = os.path.join(ROOT, "scratch", "server.err.log")

sys.path.insert(0, os.path.join(ROOT, ".deps"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

sys.stdout = open(LOG_OUT, "a", buffering=1, encoding="utf-8")
sys.stderr = open(LOG_ERR, "a", buffering=1, encoding="utf-8")
print("[launcher] starting server.py")

runpy.run_path(os.path.join(ROOT, "server.py"), run_name="__main__")
