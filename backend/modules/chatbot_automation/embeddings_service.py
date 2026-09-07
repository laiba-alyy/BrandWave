from sentence_transformers import SentenceTransformer
from typing import List

# Model load karo — pehli baar download hoga (~90MB)
print("Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded!")


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Text chunks ko vectors mein convert karta hai
    """
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings.tolist()


def generate_single_embedding(text: str) -> List[float]:
    """
    Single query ko vector mein convert karta hai
    """
    embedding = model.encode([text])
    return embedding[0].tolist()