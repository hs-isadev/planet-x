"""Keep astronomy library runtime files beside the application's disk cache."""
import os
from pathlib import Path
_runtime = Path(__file__).resolve().parents[1] / "runtime"
for kind in ("config", "cache"):
    for package in ("astropy", "astroquery"):
        (_runtime / kind / package).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_" + kind.upper() + "_HOME", str(_runtime / kind))
(_runtime / "matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_runtime / "matplotlib"))

# SPHEREx cutout headers generate repetitive Astropy INFO notices; preserve warnings/errors.
from astropy import log as _astropy_log
_astropy_log.setLevel("WARNING")
