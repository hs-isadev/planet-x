"""Install the optional, isolated local Laya Vision reviewer."""
import sys,subprocess,venv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
config=json.loads((ROOT/'backend/laya_config.json').read_text())
environment=ROOT/'runtime/laya-venv'
if not environment.exists():venv.EnvBuilder(with_pip=True,system_site_packages=True).create(environment)
python=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
subprocess.check_call([str(python),'-m','pip','install','-r',str(ROOT/'requirements-laya.txt')],cwd=ROOT)
subprocess.check_call([str(python),str(ROOT/'scripts/download_laya_model.py')],cwd=ROOT)
print('Laya Vision installed locally. Restart python start.py, open a SPHEREx sequence, then choose Review with Laya.')
