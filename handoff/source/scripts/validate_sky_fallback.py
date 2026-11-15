import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
import backend.exploration as e
from fastapi.testclient import TestClient
from backend.main import app
def unavailable(*a,**k):raise RuntimeError('Intentional offline validation')
e.tap_query=unavailable
r=TestClient(app).get('/api/earth-sky?ra=217.392321472&dec=-62.676075117')
assert r.status_code==200,r.text
d=r.json();assert d.get('partial') and len(d['objects'])>0
print('PARTIAL_REAL_CACHE',len(d['objects']),d['note'])
