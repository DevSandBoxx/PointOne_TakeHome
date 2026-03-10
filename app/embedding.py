"""
Shared embedding pipeline using sentence-transformers (same model as matters seed).
Used for embedding the time entry narrative when fetching suggestions.
"""

_MODEL = None
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def get_embedding(text: str):
    """
    Return the embedding vector for the given text (e.g. time entry narrative).
    Same model and dimension as matters table (384).
    """
    if not (text and text.strip()):
        text = " "
    model = _get_model()
    return model.encode(text.strip())
