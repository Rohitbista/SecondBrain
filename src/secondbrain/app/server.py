from fastapi import FastAPI
import uvicorn
from secondbrain.app.routes.auth import router as auth_router

app = FastAPI(title="Second Brain")

app.include_router(auth_router)

@app.get("/")
def root():
    return {"message":"Second Brain is up and running"}

def main():
    uvicorn.run(
        "secondbrain.app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )