FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY web ./web
COPY docs/GROQ_SYSTEM_PROMPT.md ./docs/GROQ_SYSTEM_PROMPT.md
COPY start.py LICENSE NOTICE ./
RUN useradd --uid 10001 --create-home observatory && mkdir -p /app/cache /app/runtime && chown -R observatory:observatory /app
USER observatory
# Bake a small, dated IRSA starter set into the image when the archive is reachable.
RUN timeout 90s python -m backend.example_field || echo "Featured cutouts will retry at runtime."
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "start.py", "--host", "0.0.0.0"]
