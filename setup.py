import subprocess
import sys
import os
import shutil
from pathlib import Path

# 定义颜色输出，提升体验
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def log(msg, color=GREEN):
    print(f"{color}[Setup] {msg}{RESET}")

def check_docker_running():
    """检查 Docker 是否安装且正在运行"""
    try:
        subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Docker 状态正常。")
    except (subprocess.CalledProcessError, FileNotFoundError):
        log("错误: Docker 未运行或未安装！请先启动 Docker Desktop。", RED)
        sys.exit(1)

def install_python_deps():
    """安装宿主机 Python 依赖"""
    log("正在安装 Python 依赖 (requirements.txt)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except subprocess.CalledProcessError:
        log("依赖安装失败，请检查网络或 pip 配置。", RED)
        sys.exit(1)

def build_docker_image():
    """构建统一的沙盒镜像"""
    image_name = "hdl-agent-sandbox:latest"
    dockerfile_path = "./sandbox" # 假设 Dockerfile 在这个目录下
    
    log(f"正在构建 Docker 镜像: {image_name} (这可能需要几分钟)...")
    if not os.path.exists(os.path.join(dockerfile_path, "Dockerfile")):
        log(f"错误: 找不到 {dockerfile_path}/Dockerfile", RED)
        sys.exit(1)

    try:
        subprocess.run(["docker", "build", "-t", image_name, dockerfile_path], check=True)
        log("Docker 镜像构建成功！")
    except subprocess.CalledProcessError:
        log("镜像构建失败。", RED)
        sys.exit(1)

def setup_env_file():
    """从模板复制 .env 文件"""
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            log("已创建 .env 文件，请稍后填入 API Key。")
        else:
            # 自动创建一个基础模板
            with open(".env", "w") as f:
                f.write("OPENAI_API_KEY=sk-xxxx\nLOG_LEVEL=INFO\n")
            log("已创建 .env 文件模板。")
    else:
        log(".env 文件已存在，跳过。")

def main():
    print("="*40)
    print("   HDL Agent 项目一键初始化工具")
    print("="*40)
    
    # 1. 环境检查
    setup_env_file()
    check_docker_running()
    
    # 2. 安装依赖
    install_python_deps()
    
    # 3. 构建 Docker
    build_docker_image()
    
    print("\n" + "="*40)
    log("环境部署完成！🎉")
    log("请确保在 .env 文件中填入了正确的 API Key。")
    log("运行 'python main.py' 启动项目。")

if __name__ == "__main__":
    main()