"""
Shared XLM-RoBERTa sentiment model — poore process mein SIRF EK dafa load hota hai.

Kyun:
    Model ~1.04 GB ka hai aur CPU par load hone mein ~14 second lagte hain.
    Agar har request par load hota to har analyze call 14s extra leti.
    Yahan ek module-level singleton rakha hai — pehli baar load hota hai,
    uske baad wahi instance sab requests share karti hain.

Kaise use karo:
    from modules.sentiment.services.model_loader import get_predictor
    predictor = get_predictor()
    results   = predictor.predict_batch(texts)

Model path env var se configure hota hai:
    SENTIMENT_MODEL_DIR=/path/to/xlm-roberta-sentiment-final
Default: modules/sentiment/models/xlm-roberta-sentiment-final/
"""

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# modules/sentiment/services/model_loader.py  ->  parents[1] = modules/sentiment
_DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parents[1] / "models" / "xlm-roberta-sentiment-final"
)


def get_model_dir() -> Path:
    """Env var jeetta hai, warna default folder."""
    return Path(os.getenv("SENTIMENT_MODEL_DIR", str(_DEFAULT_MODEL_DIR)))


# Singleton state. Lock is liye chahiye ke uvicorn ke multiple worker threads
# ek hi waqt par model load karne ki koshish na karein (do dafa 1 GB RAM).
_predictor = None
_load_failed = False
_lock = threading.Lock()


def get_predictor():
    """
    Shared SentimentPredictor wapas karo (pehli call par load karta hai).

    Model na mile ya load fail ho to None wapas aata hai — caller ko
    gracefully handle karna chahiye, server crash nahi hona chahiye.
    """
    global _predictor, _load_failed

    if _predictor is not None:
        return _predictor
    if _load_failed:
        return None

    with _lock:
        # Double-check: ho sakta hai lock ka intezar karte hue kisi aur thread
        # ne load kar diya ho.
        if _predictor is not None:
            return _predictor
        if _load_failed:
            return None

        model_dir = get_model_dir()
        if not model_dir.is_dir():
            logger.error(
                "Sentiment model directory not found: %s — "
                "sentiment predictions will be unavailable. "
                "Model weights repo mein commit nahi hote (1 GB), alag se copy karo.",
                model_dir,
            )
            _load_failed = True
            return None

        try:
            # Import yahan andar hai taake torch/transformers ka bhaari import
            # sirf tab ho jab model waqai chahiye.
            from modules.sentiment.services.inference import SentimentPredictor

            logger.info("Loading sentiment model (one time only) from %s", model_dir)
            _predictor = SentimentPredictor(str(model_dir))
            logger.info("Sentiment model ready")
            return _predictor
        except Exception as e:
            logger.error("Failed to load sentiment model: %s", e, exc_info=True)
            _load_failed = True
            return None


def warmup() -> bool:
    """
    Server startup par call karo taake pehli USER request 14s slow na ho.
    True agar model tayar hai.
    """
    return get_predictor() is not None


def is_loaded() -> bool:
    """Bina load trigger kiye batao ke model already loaded hai ya nahi."""
    return _predictor is not None
