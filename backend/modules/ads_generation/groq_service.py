import os
import json
from modules.llm_config import (
    check_raw_response,
    get_groq_config,
    post_with_retry,
    reasoning_params,
)
from modules.store_locale import market_block, market_suffix

GROQ_API_KEY, GROQ_MODEL = get_groq_config("ad_copy")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def generate_ad_copy(context: dict) -> dict:
    """
    context comes from prompt_builder.build_copy_prompt_context()
    Always grounded in the real scraped product description.
    """
    # context["brand"] BrandProfile hai (ya None). Pehle prompt ek hi mulk ka
    # naam hardcode karta tha, to har doosre mulk ke store ki ad copy mein bhi
    # usi market ke idioms aur hashtags aa jate the.
    brand = context.get("brand")

    prompt = f"""You are a marketing copywriter for an online brand{market_suffix(brand)}.
Product: {context['product_name']}
Price: {context['price']}
Category: {context['category']}
Description: {context['description']}
Desired Mood: {context.get('mood', 'not specified')}
Occasion: {context.get('occasion', 'not specified')}
CTA Goal: {context.get('cta_goal', 'Shop Now')}

{market_block(brand)}

Generate short, catchy marketing ad content based on the ACTUAL product description above.
Follow the STORE MARKET rules above: do NOT name any city or region, and do NOT
name any country other than the home country given there. This applies to the
hashtags too — no "#DubaiFashion" style location tags for a shipping destination.
Respond ONLY in valid JSON, no markdown, no explanation:
{{
  "headline": "short punchy headline, max 6 words, matching the desired mood",
  "discount_text": "short offer/price line, max 8 words",
  "cta": "call to action, max 4 words, aligned with the CTA goal",
  "caption": "1-2 sentence social media caption for this specific product",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    # Pehle max_tokens set hi nahi tha — model default par chal raha tha, yani
    # na budget ka pata tha na truncation ka. Ad copy chhoti hoti hai (headline +
    # caption + 5 hashtags, measured ~192 completion tokens), lekin gpt-oss
    # reasoning tokens bhi kharch karta hai — isliye 1,200 rakha hai.
    AD_COPY_MAX_TOKENS = 1200

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": AD_COPY_MAX_TOKENS,
        # compound* reasoning_effort par 400 deta hai — model-aware spread
        **reasoning_params(GROQ_MODEL),
    }

    # post_with_retry = wahi POST, lekin Groq 429/413 rate_limit par ek baar
    # Groq ka bataya wait kar ke dobara try karta hai.
    result = post_with_retry(
        GROQ_URL, headers=headers, payload=payload, timeout=30, what="Ad copy generation"
    )

    raw_text = check_raw_response(result, "Ad copy generation", max_tokens=AD_COPY_MAX_TOKENS)
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    return json.loads(raw_text)