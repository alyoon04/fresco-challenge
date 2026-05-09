FROM python:3.12-slim AS base

WORKDIR /app

# System deps for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

# Dev default — overridden in compose
CMD sh -c "uvicorn app.api.routes:app --host 0.0.0.0 --port ${PORT:-8000}"
