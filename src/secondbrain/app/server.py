import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from secondbrain.app.routes.auth import router as auth_router
from secondbrain.app.routes.notes import router as notes_router
from secondbrain.app.routes.search import router as search_router
from secondbrain.app.routes.users import router as user_router
from secondbrain.app.routes.admin import router as admin_router
from secondbrain.utils.embeddings import warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model before the server starts accepting requests,
    # in a thread so startup doesn't block the event loop.
    await asyncio.to_thread(warmup)
    yield


app = FastAPI(title="Second Brain", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(search_router)
app.include_router(user_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {"message": "Second Brain is up and running"}


def main():
    uvicorn.run(
        "secondbrain.app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )