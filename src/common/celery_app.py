from celery import Celery
import os
app = Celery("agvs4rtl", broker=os.getenv("CELERY_BROKER_URL"))
app.autodiscover_tasks(['src.parser', 'src.generator', 'src.verify'])
