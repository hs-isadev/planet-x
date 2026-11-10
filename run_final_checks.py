from pathlib import Path
import subprocess,sys,time,requests
root=Path(__file__).resolve().parent
for attempt in range(120):
    try:
        if requests.get('http://127.0.0.1:8000/api/health',timeout=2).status_code==200:break
    except requests.RequestException:pass
    time.sleep(.25)
else:raise RuntimeError('Start the local FastAPI server before running checks.')
result=subprocess.run([sys.executable,'prepare_live_demo.py'],cwd=root)
if result.returncode:raise SystemExit(result.returncode)
raise SystemExit(subprocess.run(['C:/Program Files/nodejs/node.exe','qa-regression.mjs'],cwd=root/'frontend').returncode)
