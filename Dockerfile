FROM python:3.13-slim

WORKDIR /app

# 系统依赖 + Node.js（前端构建）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl nodejs npm && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 前端构建
COPY frontend-v2/package*.json frontend-v2/
RUN cd frontend-v2 && npm install
COPY frontend-v2/ frontend-v2/
RUN cd frontend-v2 && npm run build

# 应用代码
COPY . .

# 数据目录
RUN mkdir -p /app/data /app/logs

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8765/api/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8765"]
