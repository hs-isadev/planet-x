import os,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('LAYA_RUNTIME_DIR') or ROOT/'runtime').resolve()
RUNTIME.mkdir(parents=True,exist_ok=True)
os.environ['HF_HOME']=str(RUNTIME/'huggingface')
os.environ['HF_HUB_DISABLE_XET']='1'
from huggingface_hub import HfApi,snapshot_download
cfg=json.loads((ROOT/'backend/laya_config.json').read_text())
repo=cfg['model']
info=HfApi().model_info(repo,revision=cfg['model_revision'])
print('Downloading public checkpoint',repo,info.sha,flush=True)
snapshot_download(repo_id=repo,revision=info.sha,local_dir=str(RUNTIME/'laya-model'),max_workers=3)
(RUNTIME/'laya-model-revision.json').write_text(json.dumps(dict(model=repo,revision=info.sha),indent=2))
print('Model download complete',flush=True)
