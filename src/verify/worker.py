from src.common.celery_app import app
@app.task(name="verify_task")
def test(): return "ok"
