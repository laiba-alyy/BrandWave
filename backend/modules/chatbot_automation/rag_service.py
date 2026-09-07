import os
import logging
from dotenv import load_dotenv
from modules.chatbot_automation.embeddings_service import generate_single_embedding
from modules.chatbot_automation.pinecone_service import search_similar
from modules.llm_config import (
    RateLimitedError,
    chat_completion,
    check_raw_response,
)
from modules.store_locale import store_country

load_dotenv()
logger = logging.getLogger(__name__)

# Key aur model ab HAR CALL par resolve hote hain (chat_completion ke andar),
# module import par nahi. Ye zaroori hai: agar ek key rate limited ho jaye to
# llm_config foran doosri par shift kar deta hai — import-time par key bandh
# lene se wo failover kabhi na chalta.
GROQ_PURPOSE = "chatbot"

# Retrieval / generation tuning
TOP_K = 5
MAX_CHUNK_CHARS = 3000       # har chunk ka max context bheja jayega
MAX_TOKENS = 600
ESCALATE_MARKER = "[ESCALATE]"

FALLBACK_RESPONSE = (
    "Sorry, I'm having trouble answering right now. "
    "I've passed this on to our team so someone can help you shortly."
)


def get_response(
    bot_id: str,
    customer_query: str,
    bot_name: str = "Assistant",
    personality: str = "helpful and friendly",
    custom_prompt: str | None = None,
    store_market: str | None = None,
) -> dict:
    """
    store_market = bot ke brand profile ki detect ki hui country (route se
    aati hai), ya None. Pehle system prompt do makhsoos zabanein hardcode
    karta tha — yani har store ek hi market ka samjha jata tha. Ab bot bas us
    zabaan mein jawab deta hai jis mein customer ne likha, aur market pata ho
    to wo context alag se lagta hai.
    """

    # Step 1: Query embedding
    query_embedding = generate_single_embedding(customer_query)

    # Step 2: Pinecone se relevant chunks
    relevant_chunks = search_similar(bot_id, query_embedding, top_k=TOP_K)

    # Step 3: Context banao — clear separators ke saath
    if relevant_chunks:
        parts = []
        for i, chunk in enumerate(relevant_chunks):
            parts.append(f"[Source {i + 1}]\n{chunk[:MAX_CHUNK_CHARS]}")
        context_with_citations = "\n\n---\n\n".join(parts)
        has_context = True
    else:
        context_with_citations = ""
        has_context = False

    # Step 4: System prompt — LLM khud decide karta hai escalation
    system_prompt = f"""You are {bot_name}, a customer service assistant. Your personality is {personality}.

HOW TO ANSWER:
- Answer ONLY from the source information provided in the user message. Never invent prices, dates, policies, or facts that are not in the sources.
- Give a COMPLETE, detailed answer. Do not cut off mid-thought and do not stop after one sentence when there is more to say.
- If the sources list multiple items (modules, features, steps, plans), list ALL of them using bullet points, with a short explanation for each.
- The chat widget shows PLAIN TEXT only, so never use markdown. No **bold**, no ### headings, no backticks. Write bullets as a line starting with "- " and use blank lines between sections.
- If the customer asks MORE THAN ONE question in a single message, answer EVERY question, each in its own clearly separated part.
- Be warm and conversational, like a helpful human agent. Do not sound robotic and do not say things like "According to Source 1" — just answer naturally.
- Always answer in the same language the customer wrote in, whichever language that is.

WHEN TO ESCALATE TO A HUMAN:
Add the exact marker {ESCALATE_MARKER} on the very last line of your reply ONLY if one of these is true:
1. The sources genuinely do not contain the information needed to answer.
2. The customer asks about a refund, a complaint, a damaged/late/wrong order, or a billing problem.
3. The customer sounds frustrated or angry, or explicitly asks to talk to a human.
4. The customer needs help specific to their own account or order that you cannot look up.

If you were able to answer the question from the sources, DO NOT add the marker. Most normal questions should NOT be escalated.
Never explain the marker and never mention it in your wording — just place it on the final line when it applies."""

    # Market context sirf tab lagta hai jab wo asal mein detect hui ho. Pata na
    # ho to koi country line jati hi nahi — bot ko ghalat mulk ka bata dena
    # "mulk nahi bataya" se zyada nuqsan-deh hai.
    if store_market:
        system_prompt += f"""

STORE MARKET:
This store sells in {store_market}. Assume the customer is shopping there
unless they say otherwise, and keep shipping, pricing, and local references
consistent with {store_market}. Never mention another country's terms."""

    # Owner ki custom instructions ko end mein add karte hain taake wo core rules
    # ko override na karein, sirf unke upar layer ho jayein.
    if custom_prompt and custom_prompt.strip():
        system_prompt += f"""

ADDITIONAL INSTRUCTIONS FROM THE BUSINESS OWNER:
{custom_prompt.strip()}

Follow these instructions unless they conflict with the answering rules above."""

    # Step 5: User prompt
    if has_context:
        user_prompt = f"""Customer message: {customer_query}

Source information:
{context_with_citations}

Answer the customer's message (all of their questions) using only the source information above."""
    else:
        user_prompt = f"""Customer message: {customer_query}

Source information: NONE

You have no source information for this. Apologise briefly, tell the customer you're passing this to the team, and add the escalation marker."""

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS
    }

    # Step 6: LLM call — error par graceful fallback, crash nahi
    try:
        result = chat_completion(
            GROQ_PURPOSE, payload, timeout=45, what="Chatbot reply"
        )
        # Truncated jawab customer ko adhoora bhejna sabse bura hai — check karo.
        # Yahan exception neeche wale except block se catch hoti hai jo graceful
        # fallback + escalation deta hai, yani customer ko adhoora reply nahi jata.
        raw_answer = check_raw_response(result, "Chatbot reply", max_tokens=MAX_TOKENS)

        if not raw_answer:
            logger.warning("Empty LLM content for bot_id=%s query=%r", bot_id, customer_query)
            raise ValueError("Empty response from model")

    # Rate limit ek WAQTI masla hai - ise neeche wale generic fallback mein
    # dabana matlab customer ko "team ko bhej diya" bol kar chup ho jana, jabke
    # asal mein bas ek minute rukna tha. Isay upar jaane do -> route 429 deti hai.
    except RateLimitedError:
        raise

    except Exception as e:
        logger.error("LLM call failed for bot_id=%s: %s", bot_id, e)
        return {
            "response": FALLBACK_RESPONSE,
            "confidence": 0.2,
            "should_escalate": True,
            "sources_found": len(relevant_chunks),
            "citations": [],
            "has_context": has_context,
        }

    # Step 7: Marker detect karo, phir response se hata do
    wants_escalation = ESCALATE_MARKER.lower() in raw_answer.lower()
    answer = _strip_marker(raw_answer)

    if not answer:
        answer = FALLBACK_RESPONSE
        wants_escalation = True

    # Step 8: Confidence
    confidence = calculate_confidence(has_context, wants_escalation)

    # Step 9: Citations list (UI preview)
    citations = []
    if has_context:
        for i, chunk in enumerate(relevant_chunks):
            citations.append({
                "source": f"Source {i + 1}",
                "text": chunk[:100] + ("..." if len(chunk) > 100 else "")
            })

    return {
        "response": answer,
        "confidence": confidence,
        "should_escalate": wants_escalation,
        "sources_found": len(relevant_chunks),
        "citations": citations,
        "has_context": has_context,
    }


def _strip_marker(text: str) -> str:
    """[ESCALATE] marker ko response se hata deta hai (case-insensitive)."""
    cleaned = text
    lowered = cleaned.lower()
    marker = ESCALATE_MARKER.lower()

    while marker in lowered:
        start = lowered.index(marker)
        cleaned = cleaned[:start] + cleaned[start + len(marker):]
        lowered = cleaned.lower()

    return cleaned.strip()


def calculate_confidence(has_context: bool, wants_escalation: bool) -> float:
    """
    Confidence ab sirf context aur LLM ke escalation decision par depend karta hai —
    normal words par phrase-matching nahi hoti.
    """
    if not has_context:
        return 0.2
    if wants_escalation:
        return 0.4
    return 0.9
