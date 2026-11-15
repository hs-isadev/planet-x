"""Run unit checks that do not require Windows socketpair/ASGI or live services.

The full pytest suite remains the normal check. This selection is useful in
restricted executors where creating an asyncio loop itself is forbidden.
"""
import ast,sys,uuid
from pathlib import Path
import pytest
root=Path(__file__).resolve().parents[1]
selected=[];excluded=[]
for path in sorted((root/'tests').glob('test_*.py')):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if not isinstance(node,ast.FunctionDef) or not node.name.startswith('test_'):continue
        uses_client=any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='TestClient' for n in ast.walk(node))
        if uses_client or path.name=='test_live_wise.py':excluded.append(node.name);continue
        selected.append(str(path)+'::'+node.name)
print('Socket-dependent/live checks excluded:',', '.join(excluded),flush=True)
base=root/'runtime'/('unit-checks-'+uuid.uuid4().hex)
raise SystemExit(pytest.main(['-q','--disable-warnings','--basetemp='+str(base),*selected]))
