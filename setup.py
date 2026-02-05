#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil

# 颜色定义
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def log(msg, color=GREEN):
    print(f"{color}[HDL-Setup] {msg}{RESET}")

def run_cmd(cmd, exit_on_fail=True):
    """运行 Shell 命令"""
    try:
        # shell=True 允许使用复合命令，但要注意安全
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError:
        log(f"命令执行失败: {cmd}", RED)
        if exit_on_fail:
            sys.exit(1)

def check_env():
    """检查 Docker 环境"""
    log("1. 环境自检...")
    
    if shutil.which("docker") is None:
        log("错误: 未找到 Docker。", RED)
        sys.exit(1)

    # 检查是否有 docker compose (新版) 或 docker-compose (旧版)
    has_compose_plugin = subprocess.run("docker compose version", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    has_compose_legacy = shutil.which("docker-compose") is not None

    if not (has_compose_plugin or has_compose_legacy):
        log("错误: 未找到 Docker Compose。", RED)
        sys.exit(1)
        
    return "docker compose" if has_compose_plugin else "docker-compose"

def setup_files():
    """初始化目录和配置"""
    log("2. 初始化目录结构...")
    
    # 确保关键目录存在
    os.makedirs("deploy", exist_ok=True)
    os.makedirs("data/workspace", exist_ok=True)
    os.makedirs("data/ip_library", exist_ok=True)
    os.makedirs("data/config/keys", exist_ok=True)
    os.makedirs("app", exist_ok=True)

    # 创建一个空的 main.py 防止报错
    if not os.path.exists("app/main.py"):
        with open("app/main.py", "w") as f:
            f.write("import time\nprint('HDL-Agent Started...')\nwhile True: time.sleep(10)")

    log("已初始化 config 目录，API Key 需通过 TUI 输入并加密保存。", YELLOW)

def start_containers(compose_cmd):
    """启动容器"""
    log("3. 构建并启动容器 (Docker Compose)...")
    
    # 停止旧的
    run_cmd(f"{compose_cmd} down", exit_on_fail=False)
    
    # 启动
    # -d 后台运行
    run_cmd(f"{compose_cmd} up -d")
    
    log("容器组已启动！")
    print("-" * 40)
    print(f"{YELLOW}开发环境就绪。{RESET}")
    print(f"进入大脑容器:  {GREEN}docker exec -it hdl_agent_core bash{RESET}")
    print(f"查看日志:      {GREEN}{compose_cmd} logs -f{RESET}")
    print("-" * 40)

def main():
    if not os.path.exists("setup.py"):
        log("请在项目根目录下运行此脚本！", RED)
        sys.exit(1)

    compose_cmd = check_env()
    setup_files()
    start_containers(compose_cmd)

if __name__ == "__main__":
    main()