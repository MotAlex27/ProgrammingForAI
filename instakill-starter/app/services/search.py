"""Application service coordinating post embeddings and semantic retrieval."""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.domain.models import Post
from app.search.retrieval import SearchDocument, retrieve_top_k


class TextEncoder(Protocol):
    def encode(self, texts: Sequence[str]) -> NDArray[np.floating]: ...


class SearchService:
    def __init__(self, posts: Sequence[Post], encoder: TextEncoder) -> None:
        self._encoder = encoder
        self._documents = tuple(
            SearchDocument(
                post_id=post.id,
                user_id=post.user_id,
                content=post.content,
            )
            for post in posts
            if post.id is not None
        )
        if len(self._documents) != len(posts):
            raise ValueError("Every indexed post must have an ID.")
        self._vectors = (
            np.asarray(encoder.encode([document.content for document in self._documents]))
            if self._documents
            else np.empty((0, 0), dtype=np.float32)
        )
        if self._vectors.ndim != 2 or self._vectors.shape[0] != len(self._documents):
            raise ValueError("The encoder must return one vector per post.")

    def search(self, query: str, limit: int) -> list[dict[str, int | str | float]]:
        if not self._documents:
            return []
        query_vectors = self._encoder.encode([query])
        if query_vectors.shape[0] != 1:
            raise ValueError("The encoder must return one vector per query.")
        results = retrieve_top_k(
            query_vectors[0],
            self._vectors,
            self._documents,
            limit,
        )
        return [
            {
                "post_id": result.document.post_id,
                "user_id": result.document.user_id,
                "content": result.document.content,
                "score": result.score,
            }
            for result in results
        ]
