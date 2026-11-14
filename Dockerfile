FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY web ./web
COPY docs/GROQ_SYSTEM_PROMPT.md ./docs/GROQ_SYSTEM_PROMPT.md
COPY start.py LICENSE NOTICE ./
COPY scripts/prefetch_lab.py ./scripts/prefetch_lab.py
# Ship bytecode: the runtime user cannot write __pycache__, so without this every cold start recompiles the app.
RUN python -m compileall -q backend start.py scripts
RUN useradd --uid 10001 --create-home observatory && mkdir -p /app/cache /app/runtime && chown observatory:observatory /app/cache /app/runtime
USER observatory
# The five preset snapshots and their original-pixel FITS cutouts are part of backend/data.
# Vesta uses its two bundled reference exposures.
RUN python -c "from backend.example_field import prepare_starter; prepare_starter('vesta')"
ENV PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPHEREX_PREWARM=0 SPHEREX_LOW_MEMORY=1
EXPOSE 8000
CMD ["python", "start.py", "--host", "0.0.0.0"]
