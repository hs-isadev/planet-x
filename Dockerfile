FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY web ./web
COPY start.py LICENSE NOTICE ./
RUN useradd --uid 10001 --create-home observatory && mkdir -p /app/cache /app/runtime && chown -R observatory:observatory /app
USER observatory
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "start.py", "--host", "0.0.0.0"]
