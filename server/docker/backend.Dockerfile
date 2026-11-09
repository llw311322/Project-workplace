# ============================================
# FastAPI 后端 Dockerfile
# ============================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---------- 依赖安装层（利用 Docker 缓存）----------
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ---------- 源码层 ----------
COPY agent/          ./agent/
COPY tools/          ./tools/
COPY utils/          ./utils/
COPY memory/         ./memory/
COPY backend/        ./backend/
COPY rag/            ./rag/
COPY .env.example    ./.env.example

# ---------- 运行时 ----------
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--loop", "uvloop", \
     "--timeout-keep-alive", "30"]
