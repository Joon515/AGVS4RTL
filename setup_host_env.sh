#!/bin/bash

echo "========================================"
echo "🚀 初始化 AGVS4RTL 宿主机 Python 运行环境"
echo "========================================"

VENV_DIR=".venv"

# 1. 检查 Python3 环境并支持自动安装
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "⚠️ 未检测到 Python 3 环境，准备自动安装 Python 3.11 稳定版..."
    if command -v apt-get &> /dev/null; then
        echo "🔧 检测到 Debian/Ubuntu 系统，请求 sudo 权限使用 apt-get 安装..."
        sudo apt-get update
        sudo apt-get install -y software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa || true
        sudo apt-get update
        sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
        PYTHON_CMD="python3.11"
    elif command -v brew &> /dev/null; then
        echo "🔧 检测到 macOS 系统，使用 Homebrew 安装..."
        brew install python@3.11
        PYTHON_CMD="python3.11"
    else
        echo "❌ 无法自动确定操作系统的包管理器，请手动安装 Python 3.11+。"
        exit 1
    fi
fi

echo "✅ 当前使用的 Python 命令为: $PYTHON_CMD ($($PYTHON_CMD --version))"

# 2. 创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 正在创建 Python 虚拟环境: $VENV_DIR ..."
    $PYTHON_CMD -m venv $VENV_DIR
else
    echo "✅ 虚拟环境 $VENV_DIR 已存在，跳过创建步骤。"
fi

# 3. 激活虚拟环境并安装依赖
echo "🔄 激活虚拟环境并升级 pip..."
source $VENV_DIR/bin/activate
pip install --upgrade pip -q

echo "📥 正在安装依赖包 (提供 IDE 代码提示支持与外部测试运行能力)..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    pip install httpx pydantic  # fallback: 仅安装外围调用必需的核心库
fi

echo "========================================"
echo "🎉 宿主机环境配置完成！"
echo "👉 请在终端执行以下命令激活环境："
echo "    source $VENV_DIR/bin/activate"
echo "▶️ 随后您可以直接运行测试脚本："
echo "    python test_host_workflow.py"
echo "========================================"