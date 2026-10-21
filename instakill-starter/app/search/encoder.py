"""CPU sentence-embedding adapter."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray


class SentenceTransformerEncoder:
    """Load a pretrained sentence encoder on demand and encode text on CPU."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def encode(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device="cpu")
        vectors = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
