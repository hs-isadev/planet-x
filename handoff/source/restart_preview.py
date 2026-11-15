"""Stop only the project's preview listening on port 8000."""
import psutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for c in psutil.net_connections(kind='tcp'):
    if c.laddr and c.laddr.port==8000 and c.status=='LISTEN' and c.pid:
        process=psutil.Process(c.pid);args=process.cmdline()
        owned=Path(process.cwd()).resolve()==ROOT and ('backend.main:app' in args or 'start.py' in args)
        assert owned,'Port is owned by a different application'
        for child in process.children(recursive=True):
            try:
                if Path(child.cwd()).resolve()==ROOT and 'laya_worker.py' in ' '.join(child.cmdline()):child.terminate()
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        process.terminate()
        try:process.wait(8)
        except psutil.TimeoutExpired:raise RuntimeError('Owned preview did not stop in time.')
