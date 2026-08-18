"""get_embedding() + classify_intent(), backed by all-MiniLM-L6-v2 (§6.2).

The model loads once at import time and the 8 persona seed embeddings are
precomputed and cached at module load — matching the "0ms lookup, loaded
once" pattern the rest of the static assets follow (§11.3). This module is
CPU-bound local inference, so it's sync, not async (§11.4).
"""

from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

PERSONA_SEED_TEXT = {
    "casual": "casual chat, random things",
    "studying": "learning, studying, homework, school",
    "venting": "frustration, venting, angry, stressed",
    "relationship_negative": "breakup, heartbreak, cheating, sad",
    "relationship_positive": "new love, crush, happy relationship",
    "hype_bro": "motivation, energy, gym, hype",
    "deep_emotional": "existential, deep, philosophical, tragedy",
    "working": "work, professional, emails, office, career, business, collaborating",
}

CLASSIFICATION_THRESHOLD = 0.3

_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

PERSONA_EMBEDDINGS: dict = {
    key: _model.encode(text) for key, text in PERSONA_SEED_TEXT.items()
}


def get_embedding(text: str):
    """384d embedding via all-MiniLM-L6-v2."""
    return _model.encode(text)


def classify_intent(text: str) -> Optional[str]:
    """Returns one of the 8 persona keys, or None if no persona clears
    the 0.3 threshold. Does NOT fall back to "casual" (§6.2, [B1]).
    """
    emb = _model.encode(text)
    best, best_score = None, -1.0
    for key, p_emb in PERSONA_EMBEDDINGS.items():
        sim = np.dot(emb, p_emb) / (np.linalg.norm(emb) * np.linalg.norm(p_emb))
        if sim > best_score:
            best_score, best = sim, key
    return best if best_score > CLASSIFICATION_THRESHOLD else None
