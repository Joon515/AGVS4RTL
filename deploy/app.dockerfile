FROM python:3.12-slim

# 1. 安装基础工具和 Docker CLI (用于控制宿主机 Docker)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# 2. 设置工作目录
WORKDIR /app

# 3. 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 代码通过 Volume 挂载，这里不需要 COPY app /app
# 这样开发时不需要每次都 rebuild