from fastapi import FastAPI
from backend.api.routes import router

app = FastAPI(
    title="Aegis Clinical Intelligence System",
    version="1.0.0"
)

app.include_router(router)

@app.get("/")
def root():
    return {
        "message": "Aegis Clinical AI Backend Running"
    }
