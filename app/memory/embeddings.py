"""
Local embeddings using sentence-transformers (no Ollama needed).
Model: all-MiniLM-L6-v2 (384 dimensions, ~22MB)
"""
from sentence_transformers import SentenceTransformer

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def embed(text: str) -> list[float]:
    model = get_model()
    return model.encode(text, normalize_embeddings=True).tolist()