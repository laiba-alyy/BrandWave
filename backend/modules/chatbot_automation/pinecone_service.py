import os
from pinecone import Pinecone
from dotenv import load_dotenv
from typing import List
import uuid

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("brandwave-chatbot")

# all-MiniLM-L6-v2 cosine scores kaafi kam hote hain — threshold low rakha hai,
# .env mein SIMILARITY_THRESHOLD se tune kiya ja sakta hai.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.1"))


def store_embeddings(
    bot_id: str,
    chunks: List[str],
    embeddings: List[List[float]]
) -> List[str]:
    """
    Chunks aur embeddings Pinecone mein store karta hai.
    bot_id se namespace alag hoti hai har chatbot ki.
    Return: store kiye gaye vector ids — inhe document ke saath save karke
    baad mein sirf usi document ke vectors delete kiye ja sakte hain.
    """
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vectors.append({
            "id": f"{bot_id}_{uuid.uuid4().hex}",
            "values": embedding,
            "metadata": {
                "text": chunk,
                "bot_id": bot_id,
                "chunk_index": i
            }
        })

    # Batch mein store karo
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch, namespace=bot_id)

    return [v["id"] for v in vectors]


def search_similar(
    bot_id: str,
    query_embedding: List[float],
    top_k: int = 5,
    min_score: float | None = None
) -> List[str]:
    """
    Query se similar chunks dhundta hai.
    min_score: per-call threshold override; default SIMILARITY_THRESHOLD.
    """
    threshold = SIMILARITY_THRESHOLD if min_score is None else min_score

    results = index.query(
        namespace=bot_id,
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True
    )

    chunks = []
    for match in results["matches"]:
        if match["score"] >= threshold:
            chunks.append(match["metadata"]["text"])

    return chunks


def delete_bot_data(bot_id: str) -> bool:
    """
    Bot ka sara data delete karta hai (poori namespace)
    """
    index.delete(delete_all=True, namespace=bot_id)
    return True


def delete_vectors(bot_id: str, vector_ids: List[str]) -> int:
    """
    Sirf diye gaye vector ids delete karta hai — ek document hatane ke liye,
    baaki knowledge base intact rehti hai.
    Return: delete request mein bheje gaye vectors ki count.
    """
    ids = [vid for vid in (vector_ids or []) if vid]
    if not ids:
        return 0

    # Pinecone ek call mein 1000 ids tak accept karta hai
    batch_size = 1000
    for i in range(0, len(ids), batch_size):
        index.delete(ids=ids[i:i + batch_size], namespace=bot_id)

    return len(ids)


def get_bot_stats(bot_id: str) -> dict:
    """
    Bot ke vectors ki stats
    """
    stats = index.describe_index_stats()
    namespace_stats = stats.namespaces.get(bot_id, {})
    return {
        "total_vectors": namespace_stats.get("vector_count", 0),
        "bot_id": bot_id
    }