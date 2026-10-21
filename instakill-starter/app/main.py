from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.search import router as search_router
from app.db.database import init_db
from app.repositories.post_repository import PostRepository
from app.search.encoder import SentenceTransformerEncoder
from app.services.search import SearchService


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    posts = PostRepository().list_all()
    app.state.search_service = SearchService(posts, SentenceTransformerEncoder())
    yield


app = FastAPI(title="InstaKill", lifespan=lifespan)
app.include_router(search_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
