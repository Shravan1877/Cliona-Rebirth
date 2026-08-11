"""get_embedding() + classify_intent(), backed by all-MiniLM-L6-v2 (§6.2).

The model and seed persona embeddings are loaded lazily, not at import
time — Phase 1 must not trigger a model download or inference.
"""

from typing import Optional

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

_model = None
PERSONA_EMBEDDINGS: dict = {}


def _load_model():
    """Lazily load the shared all-MiniLM-L6-v2 SentenceTransformer. Not called in Phase 1."""
    raise NotImplementedError("Phase 1")


def get_embedding(text: str):
    """384d embedding via all-MiniLM-L6-v2."""
    raise NotImplementedError("Phase 1")


def classify_intent(text: str) -> Optional[str]:
    """Returns one of the 8 persona keys, or None if no persona clears
    the 0.3 threshold. Does NOT fall back to "casual" (§6.2, [B1]).
    """
    raise NotImplementedError("Phase 1")
