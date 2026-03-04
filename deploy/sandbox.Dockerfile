# 使用 Ubuntu 24.04 (自带 Python 3.10 + 稳定的 EDA 工具链)
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

#换源
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.ustc.edu.cn/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.ustc.edu.cn/ubuntu/|g' /etc/apt/sources.list

    # 安装 Verilator 和基础构建工具
RUN apt-get update && apt-get install -y \
    verilator \
    build-essential \
    python3 \
    python3-pip \
    git \
    make \
    && rm -rf /var/lib/apt/lists/*

# 安装验证相关的 Python 库
RUN pip3 install --no-cache-dir --break-system-packages\
    cocotb==1.8.1 \
    cocotb-test==0.2.5 \
    pyuvm \
    pytest

WORKDIR /workspace