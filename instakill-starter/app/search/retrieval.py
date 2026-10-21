"""Pure NumPy retrieval over precomputed document vectors."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating]
IntArray = NDArray[np.integer]


@dataclass(frozen=True)
class SearchDocument:
    post_id: int
    user_id: int
    content: str


@dataclass(frozen=True)
class SearchResult:
    document: SearchDocument
    score: float


def cosine_similarity(query_vector: FloatArray, matrix: FloatArray) -> NDArray[np.float64]:
    """Compute cosine similarity to each matrix row; zero vectors score zero."""
    query = np.asarray(query_vector, dtype=np.float64)
    vectors = np.asarray(matrix, dtype=np.float64)
    if query.ndim != 1 or vectors.ndim != 2 or vectors.shape[1] != query.shape[0]:
        raise ValueError("Expected a 1-D query and a 2-D matrix with matching dimensions.")

    query_norm = np.linalg.norm(query)
    row_norms = np.linalg.norm(vectors, axis=1)
    denominators = row_norms * query_norm
    scores = np.zeros(vectors.shape[0], dtype=np.float64)
    np.divide(vectors @ query, denominators, out=scores, where=denominators != 0)
    return scores


def top_k_indices(scores: FloatArray, post_ids: IntArray, k: int) -> NDArray[np.intp]:
    """Return indices by descending score, breaking ties by ascending post ID."""
    score_array = np.asarray(scores, dtype=np.float64)
    id_array = np.asarray(post_ids)
    if score_array.ndim != 1 or id_array.ndim != 1 or score_array.shape != id_array.shape:
        raise ValueError("Scores and post IDs must be one-dimensional arrays of equal length.")
    if k < 0:
        raise ValueError("k must be non-negative.")
    if not np.isfinite(score_array).all():
        raise ValueError("Scores must all be finite.")

    return np.lexsort((id_array, -score_array))[:k]


def retrieve_top_k(
    query_vector: FloatArray,
    document_vectors: FloatArray,
    documents: tuple[SearchDocument, ...],
    k: int,
) -> list[SearchResult]:
    """Score documents with cosine similarity and return deterministic top-k."""
    vectors = np.asarray(document_vectors)
    if vectors.ndim != 2 or vectors.shape[0] != len(documents):
        raise ValueError("Each document must have exactly one vector.")
    scores = cosine_similarity(query_vector, vectors)
    indices = top_k_indices(
        scores,
        np.asarray([document.post_id for document in documents]),
        k,
    )
    return [
        SearchResult(documents[index], float(scores[index]))
        for index in indices
    ]
