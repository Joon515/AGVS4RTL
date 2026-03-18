from src.common.celery_app import app
@app.task(name="parser_task")
def test(): return "ok"
