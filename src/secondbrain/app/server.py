import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

from secondbrain.app.routes.auth import router as auth_router
from secondbrain.app.routes.notes import router as notes_router
from secondbrain.app.routes.search import router as search_router
from secondbrain.app.routes.users import router as user_router
from secondbrain.app.routes.admin import router as admin_router
from secondbrain.app.routes.chat import router as chat_router
from secondbrain.utils.embeddings import warmup
from secondbrain.config.settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model before the server starts accepting requests,
    # in a thread so startup doesn't block the event loop.
    await asyncio.to_thread(warmup)
    yield


app = FastAPI(title="Second Brain", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(search_router)
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(chat_router)


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