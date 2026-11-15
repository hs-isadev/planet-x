"""Warm the observatory cache. Run with python -m scripts.prefetch_lab."""
from backend.observation_lab_core.warm_cache import main

if __name__ == '__main__':
    raise SystemExit(main())
