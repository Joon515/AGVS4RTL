# 使用 Python 3.12 (性能更好)
FROM python:3.12-slim

RUN sed -i 's|deb.debian.org/debian|mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|security.debian.org/debian-security|mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources
# 安装 Docker CLI (用于向宿主机发号施令)
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
    git \
    docker.io \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从构建上下文(根目录)复制依赖清单
COPY requirements.txt .
RUN ls -la requirements.txt && echo "---START---" && cat requirements.txt && echo "---END---"
# 安装依赖
# 将第 19 行修改为：
RUN pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装 debugpy 方便未来远程调试
RUN pip install debugpy

# 源码通过 Volume 挂载，无需 COPY