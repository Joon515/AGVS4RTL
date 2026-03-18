from celery import Celery
import os

# 从环境变量获取 Redis 地址，默认指向 docker-compose 中的 redis 服务名
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

app = Celery(
    "agvs4rtl",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.parser.worker",
        "src.generator.worker",
        "src.verify.worker"
    ]
)

# 基础配置
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)