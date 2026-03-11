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

# 设置 UTF-8 locale，避免 Python surrogateescape 导致中文输入损坏
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

# 从构建上下文(根目录)复制依赖清单
COPY requirements.txt requirements-dev.txt ./
RUN ls -la requirements*.txt && echo "---START requirements-dev.txt---" && cat requirements-dev.txt && echo "---END requirements-dev.txt---"
# 安装依赖（包含开发依赖，便于在容器内直接运行测试）
RUN pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements-dev.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装 debugpy 方便未来远程调试
RUN pip install debugpy

# 源码通过 Volume 挂载，无需 COPY