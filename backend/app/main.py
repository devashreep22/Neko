from fastapi import FastAPI
from app.services.analytics import generate_daily_report
from app.services.current_activity import get_current_activity

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Welcome to NekoAI Backend"}

@app.get("/health")
def health():
    return {"status": "running"}

@app.get("/report")
def daily_report():
    return generate_daily_report()

@app.get("/current-activity")
def current_activity():
    return get_current_activity()