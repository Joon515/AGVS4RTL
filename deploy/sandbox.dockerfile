FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# 1. 安装 EDA 工具链
RUN apt-get update && apt-get install -y \
    verilator \
    build-essential \
    python3 \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装验证库
RUN pip3 install --no-cache-dir cocotb cocotb-test pyuvm pytest

WORKDIR /workspace