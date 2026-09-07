"""
XLM-RoBERTa Multilingual Sentiment Classifier — inference library + CLI.

Importable as a library (this is how the API uses it):
    from modules.sentiment.services.inference import SentimentPredictor, clean_text
    predictor = SentimentPredictor(model_dir)
    results   = predictor.predict_batch(["bohat acha product hai", "worst quality"])

Still runnable as a CLI (nothing below runs on import — see `if __name__`):
    python inference.py --model_dir ./xlm-roberta-sentiment-final
    python inference.py --model_dir ./xlm-roberta-sentiment-final --text "bohat acha product hai 🔥"
    python inference.py --model_dir ./xlm-roberta-sentiment-final --file reviews.txt
    python inference.py --model_dir ./xlm-roberta-sentiment-final --interactive

Requirements:
    pip install transformers torch emoji
"""

import argparse
import json
import logging
import os
import re
import sys
import unicodedata

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

logger = logging.getLogger(__name__)

# `emoji` sirf demojize ke liye chahiye. Agar wo install na ho to poora sentiment
# module import par crash ho jata tha (aur uske saath FastAPI server bhi).
# Ab wo optional hai: emoji na ho to text bina demojize ke clean hota hai.
try:
    import emoji as _emoji

    _HAS_EMOJI = True
except ImportError:  # pragma: no cover
    _emoji = None
    _HAS_EMOJI = False
    logger.warning(
        "`emoji` package not installed — emoji will be stripped instead of "
        "converted to words. Install it with: pip install emoji"
    )


# ═══════════════════════════════════════════════════════════════════
#  TEXT CLEANING PIPELINE  (mirrors the training notebook exactly)
# ═══════════════════════════════════════════════════════════════════

ROMAN_URDU_MAP = {
    r"\bbht\b": "bohat",
    r"\bbhot\b": "bohat",
    r"\bbohot\b": "bohat",
    r"\bbuht\b": "bohat",
    r"\bbahut\b": "bohat",
    r"\bacha\b": "acha",
    r"\bachha\b": "acha",
    r"\baccha\b": "acha",
    r"\bach+a\b": "acha",
    r"\bnhi\b": "nahi",
    r"\bnai\b": "nahi",
    r"\bnh?i+\b": "nahi",
    r"\bkrna\b": "karna",
    r"\bkrn\b": "karna",
    r"\bkro\b": "karo",
    r"\bkrny\b": "karne",
    r"\bhaa?i?n\b": "haan",
    r"\bha+n+\b": "haan",
    r"\bh+a+\b": "ha",
    r"\bphr\b": "phir",
    r"\bmein\b": "mein",
    r"\bkbi\b": "kabhi",
    r"\bkbhi\b": "kabhi",
    r"\bmsla\b": "masla",
    r"\bmslaa\b": "masla",
    r"\bplz\b": "please",
    r"\bpls\b": "please",
    r"\bthnx\b": "thanks",
    r"\bthnks\b": "thanks",
    r"\bthx\b": "thanks",
    r"\bty\b": "thank you",
    r"\bu\b": "you",
    r"\br\b": "are",
    r"\bur\b": "your",
    r"\bn\b": "and",
    r"\bb4\b": "before",
    r"\bm\b": "main",
}

_ROMAN_URDU_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in ROMAN_URDU_MAP.items()
]


def clean_text(text: str) -> str:
    """Full cleaning pipeline for multilingual (EN + Roman Urdu) text."""
    if not isinstance(text, str) or not text.strip():
        return ""

    text = unicodedata.normalize("NFKC", text)
    if _HAS_EMOJI:
        text = _emoji.demojize(text, delimiters=(" ", " "))
    text = re.sub(r":(\w+):", r"\1", text)
    text = text.replace("_", " ")
    text = text.lower()
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\S+@\S+\.\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(
        r"#(\S+)",
        lambda m: re.sub(r"([a-z])([A-Z])", r"\1 \2", m.group(1)).lower(),
        text,
    )
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"[^a-z0-9\s.,!?'\u0600-\u06FF]", " ", text)
    # Koi bhi character jo 3+ baar repeat ho use 2 par le aao:
    #   "greatttt" -> "greatt",  "!!!" -> "!!"
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)
    # Ab repeated punctuation ko EK par le aao: "!!" -> "!", "??" -> "?"
    # BUG THA: pattern `([!?.])\\1+` mein double backslash tha, jo regex ke liye
    # ek LITERAL backslash + "1" banta hai — yani ye sirf `!\1` jaise text par
    # match karta tha, asli reviews par kabhi nahi. Line effectively no-op thi.
    # Single `\1` backreference hai, jo pehle group ko dobara match karta hai.
    text = re.sub(r"([!?.])\1+", r"\1", text)

    for pattern, replacement in _ROMAN_URDU_PATTERNS:
        text = pattern.sub(replacement, text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


# ═══════════════════════════════════════════════════════════════════
#  SENTIMENT PREDICTOR
# ═══════════════════════════════════════════════════════════════════

LABEL2ID = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
SENTIMENT_ICONS = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}


class SentimentPredictor:
    """Load a saved XLM-RoBERTa sentiment model and run inference."""

    def __init__(self, model_dir: str, max_length: int = 128):
        self.max_length = max_length
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load config if available
        config_path = os.path.join(model_dir, "training_config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                self.training_config = json.load(f)
            self.max_length = self.training_config.get("max_length", max_length)
        else:
            self.training_config = None

        logger.info("Loading sentiment model from: %s (device=%s)", model_dir, self.device)

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        # MEMORY NOTE: ye model float32 mein ~1.1 GB RAM leta hai (xlm-roberta-base,
        # 278M params). Backend usi process mein chatbot ka MiniLM bhi load karta
        # hai, to 8 GB machine par agar free RAM ~1.5 GB se kam ho to load
        # segfault (exit 139) kar deta hai. Ye code ka masla nahi — machine par
        # jagah chahiye.
        #
        # `low_cpu_mem_usage=True` yahan MAT lagao: transformers v5 mein wo
        # argument chup-chaap discard ho jata hai (modeling_utils.py mein
        # "Not used anymore" list) — memory-efficient loading ab default hai.
        # Wo lagane se sirf ye ghalat-fehmi hoti hai ke kuch optimize ho raha hai.
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.to(self.device)
        self.model.eval()

        logger.info("Sentiment model loaded successfully (max_length=%d)", self.max_length)

    def predict(self, text: str) -> dict:
        """Predict sentiment for a single text with confidence scores."""
        cleaned = clean_text(text)
        if not cleaned:
            return self._empty_result(text)

        inputs = self.tokenizer(
            cleaned,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).cpu().numpy()[0]

        pred_id = int(np.argmax(probs))
        return {
            "original_text": text,
            "cleaned_text": cleaned,
            "prediction": ID2LABEL[pred_id],
            "confidence": float(probs[pred_id]),
            "scores": {
                "negative": float(probs[0]),
                "neutral": float(probs[1]),
                "positive": float(probs[2]),
            },
        }

    @staticmethod
    def _empty_result(text: str) -> dict:
        """Wo texts jo clean hone ke baad khali reh jate hain."""
        return {
            "original_text": text,
            "cleaned_text": "",
            "prediction": "neutral",
            "confidence": 0.0,
            "scores": {"negative": 0.0, "neutral": 0.0, "positive": 0.0},
        }

    def predict_batch(self, texts: list[str], batch_size: int = 32) -> list[dict]:
        """
        Predict sentiment for many texts in REAL batches.

        Pehle ye `predict()` ko ek-ek kar ke loop karta tha — yani 20 reviews ke
        liye 20 alag tokenizer calls aur 20 alag model forward passes. Ab saare
        texts ek saath tokenize hote hain aur ek hi forward pass mein jate hain,
        jo CPU par kaafi tez hai.

        Return shape bilkul wahi hai jo `predict()` deta hai (list of dicts with
        prediction / confidence / scores / cleaned_text / original_text), aur
        order input ke order jaisa hi rehta hai.
        """
        if not texts:
            return []

        # Khali/whitespace texts model ko bhejne ka fayda nahi — unke liye seedha
        # neutral result rakh lo, aur baqi ko unke original index ke saath batch
        # karo taake final order na bigde.
        results: list[dict | None] = [None] * len(texts)
        pending_idx: list[int] = []
        pending_clean: list[str] = []

        for i, raw in enumerate(texts):
            cleaned = clean_text(raw)
            if not cleaned:
                results[i] = self._empty_result(raw)
            else:
                pending_idx.append(i)
                pending_clean.append(cleaned)

        for start in range(0, len(pending_clean), batch_size):
            chunk_idx = pending_idx[start : start + batch_size]
            chunk_txt = pending_clean[start : start + batch_size]

            # EK tokenizer call — padding=True poore chunk ko longest par pad karta hai
            inputs = self.tokenizer(
                chunk_txt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.max_length,
            ).to(self.device)

            # EK forward pass poore chunk ke liye
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1).cpu().numpy()

            for row, (orig_i, cleaned) in enumerate(zip(chunk_idx, chunk_txt)):
                p = probs[row]
                pred_id = int(np.argmax(p))
                results[orig_i] = {
                    "original_text": texts[orig_i],
                    "cleaned_text": cleaned,
                    "prediction": ID2LABEL[pred_id],
                    "confidence": float(p[pred_id]),
                    "scores": {
                        "negative": float(p[0]),
                        "neutral": float(p[1]),
                        "positive": float(p[2]),
                    },
                }

        return [r for r in results if r is not None]

    def print_result(self, result: dict) -> None:
        """Pretty-print a prediction result."""
        sentiment = result["prediction"]
        conf = result["confidence"]
        icon = SENTIMENT_ICONS[sentiment]

        print(f"\n{icon} [{sentiment.upper():>8s}]  confidence: {conf:.1%}")
        print(f"   Original: {result['original_text']}")
        print(f"   Cleaned:  {result['cleaned_text']}")
        print(
            f"   Scores:   neg={result['scores']['negative']:.3f}  "
            f"neu={result['scores']['neutral']:.3f}  "
            f"pos={result['scores']['positive']:.3f}"
        )


# ═══════════════════════════════════════════════════════════════════
#  CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="XLM-RoBERTa Multilingual Sentiment Classifier — Inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python inference.py --model_dir ./xlm-roberta-sentiment-final --text "bohat acha product 🔥"
  python inference.py --model_dir ./xlm-roberta-sentiment-final --file reviews.txt
  python inference.py --model_dir ./xlm-roberta-sentiment-final --interactive
        """,
    )
    parser.add_argument(
        "--model_dir",
        type=str,
        required=True,
        help="Path to the saved model directory",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Single text to classify",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to a text file with one review per line",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start interactive mode (type reviews, get predictions)",
    )
    parser.add_argument(
        "--max_length",
        type=int,
        default=128,
        help="Max token length (default: 128)",
    )
    parser.add_argument(
        "--json_output",
        action="store_true",
        help="Output results as JSON instead of pretty-printed text",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.model_dir):
        print(f" Model directory not found: {args.model_dir}")
        sys.exit(1)

    predictor = SentimentPredictor(args.model_dir, max_length=args.max_length)

    # ── Single text mode ──
    if args.text:
        result = predictor.predict(args.text)
        if args.json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            predictor.print_result(result)
        return

    # ── File mode ──
    if args.file:
        if not os.path.isfile(args.file):
            print(f" File not found: {args.file}")
            sys.exit(1)

        with open(args.file, encoding="utf-8") as f:
            reviews = [line.strip() for line in f if line.strip()]

        print(f"Processing {len(reviews)} reviews...\n")
        print("═" * 70)

        results = predictor.predict_batch(reviews)
        if not args.json_output:
            for result in results:
                predictor.print_result(result)

        if args.json_output:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            # Summary
            sentiments = [r["prediction"] for r in results]
            print("\n" + "═" * 70)
            print(f"\n Summary ({len(results)} reviews):")
            for s in ["positive", "neutral", "negative"]:
                count = sentiments.count(s)
                pct = count / len(sentiments) * 100
                print(f"   {SENTIMENT_ICONS[s]} {s:>8s}: {count:3d} ({pct:.1f}%)")
        return

    # ── Interactive mode ──
    if args.interactive:
        print("═" * 70)
        print("   Interactive Sentiment Classifier")
        print("  Type a review and press Enter. Type 'quit' or 'exit' to stop.")
        print("═" * 70)

        while True:
            try:
                text = input("\n Review > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye! ")
                break

            if text.lower() in ("quit", "exit", "q"):
                print("\nGoodbye! ")
                break

            if not text:
                continue

            result = predictor.predict(text)
            if args.json_output:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                predictor.print_result(result)
        return

    # ── No mode specified → run demo ──
    print("No input specified. Running demo predictions...\n")
    demo_reviews = [
        "bhot acha product ha, bohat khush hun mein! 🔥🔥",
        "worst quality, waste of money 😡",
        "product okay hai, nothing special",
        "Love this!! Best purchase ever thnx seller 💕",
        "ye cheez bilkul kharab hai, refund kro plz",
        "delivery was on time, packaging was decent",
        "bohat bura experience tha, never buying again",
        "Amazing quality at this price point! Highly recommended 👏",
    ]

    print("═" * 70)
    print("              SENTIMENT PREDICTIONS (Demo)")
    print("═" * 70)
    for review in demo_reviews:
        result = predictor.predict(review)
        predictor.print_result(result)
    print("\n" + "═" * 70)
    print("\n Tip: Use --text, --file, or --interactive for custom input.")


if __name__ == "__main__":
    main()
