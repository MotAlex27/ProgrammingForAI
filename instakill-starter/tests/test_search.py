import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.search import get_search_service, router
from app.domain.models import Post
from app.search.retrieval import (
    SearchDocument,
    cosine_similarity,
    retrieve_top_k,
    top_k_indices,
)
from app.services.search import SearchService


class FakeEncoder:
    def __init__(self, vectors_by_text):
        self.vectors_by_text = vectors_by_text

    def encode(self, texts):
        return np.asarray([self.vectors_by_text[text] for text in texts], dtype=np.float32)


def make_service():
    posts = [
        Post(id=20, user_id=2, content="budget dinner"),
        Post(id=10, user_id=1, content="cheap restaurant"),
        Post(id=30, user_id=3, content="quiet library"),
    ]
    encoder = FakeEncoder({
        "budget dinner": [1, 0],
        "cheap restaurant": [1, 0],
        "quiet library": [0, 1],
        "meal near campus": [1, 0],
        " meal near campus ": [1, 0],
    })
    return SearchService(posts, encoder)


def test_cosine_similarity_handles_zero_vectors():
    scores = cosine_similarity(np.array([0.0, 0.0]), np.array([[1.0, 0.0], [0.0, 0.0]]))

    assert np.array_equal(scores, np.array([0.0, 0.0]))


def test_top_k_sorts_by_score_then_post_id():
    indices = top_k_indices(np.array([0.5, 0.5, 0.9]), np.array([20, 10, 30]), 3)

    assert np.array_equal(indices, np.array([2, 1, 0]))


def test_retrieve_top_k_returns_ordered_results_and_honors_limit():
    documents = (
        SearchDocument(20, 2, "budget dinner"),
        SearchDocument(10, 1, "cheap restaurant"),
        SearchDocument(30, 3, "quiet library"),
    )
    vectors = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

    results = retrieve_top_k(np.array([1.0, 0.0]), vectors, documents, 2)

    assert [result.document.post_id for result in results] == [10, 20]
    assert [result.score for result in results] == [1.0, 1.0]


def test_search_service_embeds_query_and_returns_api_fields():
    results = make_service().search("meal near campus", 2)

    assert [result["post_id"] for result in results] == [10, 20]
    assert set(results[0]) == {"post_id", "user_id", "content", "score"}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_search_service] = lambda: make_service()
    return TestClient(app)


def test_search_endpoint_returns_original_query_and_ranked_results(client):
    response = client.get("/search", params={"q": " meal near campus ", "limit": 2})

    assert response.status_code == 200
    assert response.json()["query"] == " meal near campus "
    assert [item["post_id"] for item in response.json()["results"]] == [10, 20]


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"limit": 5}, 422),
        ({"q": "", "limit": 5}, 422),
        ({"q": "   ", "limit": 5}, 422),
        ({"q": "dinner", "limit": 0}, 422),
        ({"q": "dinner", "limit": 21}, 422),
        ({"q": "dinner", "limit": "many"}, 422),
        ({"q": "dinner"}, 422),
    ],
)
def test_search_endpoint_rejects_invalid_parameters(client, params, expected_status):
    assert client.get("/search", params=params).status_code == expected_status
