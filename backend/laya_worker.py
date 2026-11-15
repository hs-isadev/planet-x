"""Local JSON-lines inference worker, isolated from the application's Python dependencies."""
import sys,os,json,traceback,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('LAYA_RUNTIME_DIR') or ROOT/'runtime').resolve()
os.environ['TORCHINDUCTOR_CACHE_DIR']=str(RUNTIME/'torch-inductor')
os.environ['TORCH_HOME']=str(RUNTIME/'torch')
os.environ['TRITON_CACHE_DIR']=str(RUNTIME/'triton')
os.environ['HF_HOME']=str(RUNTIME/'huggingface')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_XET']='1'
agent=None
for line in sys.stdin:
    request={}
    try:
        request=json.loads(line)
        request_id=request.get('request_id')
        with contextlib.redirect_stdout(sys.stderr):
            import torch,laya
            from PIL import Image
            if agent is None:
                print(json.dumps({'request_id':request_id,'stage':'loading_model'}),file=sys.__stdout__,flush=True)
                torch.set_num_threads(4)
                agent=laya.load_vlm(str(RUNTIME/'laya-model'),device='cuda' if torch.cuda.is_available() else 'cpu',dtype='fp32')
                agent.model.float()  # Keep the vision connector and embeddings in the same dtype.
            print(json.dumps({'request_id':request_id,'stage':'running_inference'}),file=sys.__stdout__,flush=True)
            result=agent.predict({'image':Image.open(request['image']).convert('RGB'),'note':request['note']},{
                'change':{'type':'choice','instructions':request.get('instructions','Compare the source or chronological panels described in the note. Decide visible change, not its cause. Images share a registered grid and signal-to-noise scale. Masked pixels are unknown. Prefer coherent changes over isolated noise; if unclear choose uncertain.'),'criteria':['appeared or brightened','disappeared or faded','shifted position','stable or no convincing change','artifact or missing data','uncertain']}
            })
        print(json.dumps({'request_id':request_id,'ok':True,'result':result},default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),flush=True)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'request_id':request.get('request_id') if isinstance(request,dict) else None,'ok':False,'error':type(exc).__name__+': '+str(exc)}),flush=True)
