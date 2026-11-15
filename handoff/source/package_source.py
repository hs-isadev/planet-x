"""Package the current no-build application, excluding historical UI and runtime caches."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib
root=Path(__file__).resolve().parent;out=root/'release'/'planet-x-observatory.zip';out.parent.mkdir(exist_ok=True)
roots=['backend','web','tests','scripts','qa','third_party']
files=[root/name for name in ['README.md','LICENSE','NOTICE','requirements.txt','requirements-laya.txt','start.py','restart_preview.py','Dockerfile','pytest.ini','package_source.py','.gitignore','.dockerignore']]
for name in roots:
    files.extend(p for p in (root/name).rglob('*') if p.is_file())
files.extend(p for p in (root/'docs/data-proof').rglob('*') if p.is_file())
files.extend(root/'docs'/name for name in ['CURRENT_STATUS.md','current-validation.json','preset-live-validation.json','catalog-overlay-live-validation.json','nearby-live-validation.json','exploration-validation.json','motion-navigation-validation.json','laya-live-validation.json','laya-auto-reference-validation.json','continuous-world-validation.json','science-acceptance.json','science-context-validation.json','final-core-validation.json','barnard-loaded-motion.json','barnard-current-manifest.json','barnard-full-download-status.json','laya-full-sequence-validation.json','lightcurve-rw.json','lightcurve-rdraconis.json'])
files.append(root/'docs/live-barnard-difference.png')
files.extend(root/'docs'/name for name in ['revision-validation.json','revision-laya-loaded.json','cache-audit.json','review-barnard-difference.png','REVISION_CHANGES.md'])
excluded={'node_modules','__pycache__','.pytest_cache','.git','.venv'}
with ZipFile(out,'w',ZIP_DEFLATED) as z:
 for f in sorted(set(files)):
  if not f.exists():continue
  rel=f.relative_to(root)
  if f.name in {'earth-hgt.gz','moon-dem.tif','moon-dem.npy'}:continue
  if any(part in excluded for part in rel.parts) or f.suffix=='.log' or f.name.endswith('-links.json') or f.name.endswith('-source.jpg'):continue
  # Diagnostic/one-off scripts are not application prerequisites.
  if rel.parts[0]=='scripts' and f.name in ['diagnose_simbad.py','check_presets.py','simbad_mirror.py','fetch_assets.py','finish_assets.py','validate_context.py']:continue
  z.write(f,Path('planet-x')/rel)
with ZipFile(out) as z:
 assert z.testzip() is None
 assert all('planet-x/'+p in z.namelist() for p in ['web/index.html','web/app.js','backend/main.py','start.py','requirements.txt'])
 assert not any('/frontend/' in p or '/cache/' in p or '/node_modules/' in p for p in z.namelist())
 print(len(z.namelist()),'files;',out.stat().st_size,'bytes')
print(out);print('SHA256',hashlib.sha256(out.read_bytes()).hexdigest())
