"""HTTP interface for semantic post search."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.search import SearchService

router = APIRouter()


class SearchResultResponse(BaseModel):
    post_id: int
    user_id: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


def get_search_service(request: Request) -> SearchService:
    return request.app.state.search_service


@router.get("/search", response_model=SearchResponse)
def search_posts(
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)],
    service: Annotated[SearchService, Depends(get_search_service)],
) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query parameter 'q' must not be empty.")
    return SearchResponse(query=q, results=service.search(q, limit))
