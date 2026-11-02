"""HTTP interface for personalized and chronological feeds."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.feed import FeedService

router = APIRouter()


class FeedPostResponse(BaseModel):
    post_id: int
    user_id: int
    content: str
    created_at: str
    score: float | None = None


class FeedResponse(BaseModel):
    user_id: int
    strategy: Literal["for_you", "chronological"]
    posts: list[FeedPostResponse]


def get_feed_service(request: Request) -> FeedService:
    return request.app.state.feed_service


@router.get("/feed", response_model=FeedResponse, response_model_exclude_none=True)
def get_feed(
    user_id: Annotated[int, Query()],
    service: Annotated[FeedService, Depends(get_feed_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    strategy: Annotated[Literal["for_you", "chronological"], Query()] = "for_you",
) -> FeedResponse:
    try:
        result = service.get_feed(user_id, limit, strategy)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FeedResponse.model_validate(result)
