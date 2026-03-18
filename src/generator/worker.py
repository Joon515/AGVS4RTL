from src.common.celery_app import app
@app.task(name="generator_task")
def test(): return "ok"
