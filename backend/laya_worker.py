"""Local JSON-lines inference worker, isolated from the application's Python dependencies."""
import sys,os,json,traceback,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['TORCHINDUCTOR_CACHE_DIR']=str(ROOT/'runtime/torch-inductor')
os.environ['TORCH_HOME']=str(ROOT/'runtime/torch')
os.environ['TRITON_CACHE_DIR']=str(ROOT/'runtime/triton')
os.environ['HF_HOME']=str(ROOT/'runtime/huggingface')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_XET']='1'
agent=None
for line in sys.stdin:
    try:
        request=json.loads(line)
        with contextlib.redirect_stdout(sys.stderr):
            import torch,laya
            from PIL import Image
            if agent is None:
                torch.set_num_threads(4)
                agent=laya.load_vlm(str(ROOT/'runtime/laya-model'),device='cuda' if torch.cuda.is_available() else 'cpu',dtype='fp32')
            result=agent.predict({'image':Image.open(request['image']).convert('RGB'),'note':request['note']},{
                'change':{'type':'choice','instructions':request.get('instructions','Compare the source or chronological panels described in the note. Decide visible change, not its cause. Images share a registered grid and signal-to-noise scale. Masked pixels are unknown. Prefer coherent changes over isolated noise; if unclear choose uncertain.'),'criteria':['appeared or brightened','disappeared or faded','shifted position','stable or no convincing change','artifact or missing data','uncertain']}
            })
        print(json.dumps({'ok':True,'result':result},default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),flush=True)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'ok':False,'error':str(exc)}),flush=True)
