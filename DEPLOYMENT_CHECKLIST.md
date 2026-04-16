# AGVS4RTL 宿主机环境部署清单

由于系统采用了高度容器化的设计（Parser、Gen、Verify 均在 Docker 内隔离运行），宿主机（Host）仅需要提供基础的容器运行环境和挂载卷权限配置即可完成部署。

## 1. 宿主机前置依赖

- **操作系统**: Linux (推荐 Ubuntu 20.04/22.04)、macOS 或 Windows (需启用 WSL2 后端)。
- **Docker Engine**: 版本 >= 20.10.0。
- **Docker Compose**: 推荐使用 V2 版本（即 `docker compose` 命令而非 `docker-compose`）。
- **Git**: 用于拉取代码仓库。

## 2. 源码获取与目录初始化

在宿主机上执行以下命令，准备挂载所需的物理目录：

```bash
# 1. 进入工作区并克隆代码
git clone <您的仓库地址> AGVS4RTL
cd AGVS4RTL

# 2. 创建系统所需的挂载和输出目录
mkdir -p shared_workspace
mkdir -p Output

# 3. 权限配置 (参考 DEVLOG 备注，目前暂用 777 以避免容器内无写权限导致挂载卷报错)
chmod -R 777 shared_workspace
chmod -R 777 Output
```

## 3. 环境变量配置 (.env)

系统依赖宿主机的 `USER_ID` 和 `GROUP_ID` 来映射容器内权限，避免生成的文件在宿主机上变成 `root` 归属。
请在项目根目录创建或修改 `.env` 文件：

```bash
# 获取当前宿主机用户的 UID 和 GID，并写入 .env
echo "USER_ID=$(id -u)" > .env
echo "GROUP_ID=$(id -g)" >> .env

# 补充大模型相关的 API 密钥配置 (供 Gen 和 Parser 中的 LangGraph 节点使用)
echo "OPENAI_API_KEY=your_openai_api_key_here" >> .env
echo "OPENAI_BASE_URL=https://api.openai.com/v1" >> .env
```

## 4. 容器构建与启动

拉起包含 Parser、Gen、Verify 的三容器拓扑结构：

```bash
# 构建镜像 (首次运行或修改 Dockerfile/requirements.txt 后需要执行)
docker compose build

# 后台启动服务
docker compose up -d
```

## 5. 服务探活与验证

确保容器已成功启动且端口已正确暴露给宿主机：

```bash
# 检查容器运行状态 (应看到三个 Up 状态的容器)
docker compose ps

# 探活 Parser 服务网关 (宿主机端口暴露在 8001)
curl -X GET http://localhost:8001/health
```