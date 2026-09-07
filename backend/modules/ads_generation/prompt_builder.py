from modules.store_locale import store_country


def build_image_prompt(product: dict, form_data: dict, brand=None) -> str:

    parts = []

    # User ka custom prompt sabse important
    if form_data.get("custom_prompt"):
        parts.append(form_data["custom_prompt"])

    # Mood add karo
    if form_data.get("mood"):
        parts.append(f"Visual mood: {form_data['mood']}.")

    # Occasion add karo
    if form_data.get("occasion") and form_data["occasion"] not in (None, "None"):
        parts.append(f"Occasion theme: {form_data['occasion']}.")

    # Market context — sirf tab jab detect hua ho. Is ke baghair image models
    # apna default cultural setting chun lete the (aur cloudflare_service ka
    # base prompt to Mughal garden hardcode hi karta tha).
    country = store_country(brand)
    if country:
        parts.append(
            f"Styling, setting and any people shown should suit shoppers in {country}."
        )

    return " ".join(parts)


# ── Compositing providers (Bria / Claid) ──────────────────────────────────────
# Ye do builders gpt-image-1 wale build_image_prompt se alag hain, kyunki kaam
# hi alag hai: gpt-image-1 poori tasveer dobara banata tha (is liye "product mat
# badlo" jaisi guardrails zaroori thin), jab ke Bria/Claid product ko chhoote hi
# nahi — sirf background/model banate hain. Phir bhi "koi text mat likho" wali
# guardrail dono par lagti hai, kyunki text Pillow (image_polish.py) baad mein
# lagata hai aur do layers ek doosre par charh jati hain.

NO_TEXT_GUARDRAIL = (
    "The scene must contain no text, letters, words, numbers, signage, "
    "watermarks, logos or badges of any kind."
)

BOTTOM_CLEAR_GUARDRAIL = (
    "Keep the lower third of the frame simple and uncluttered."
)


def build_scene_description(product: dict, form_data: dict, brand=None) -> str:
    """
    Bria ka `scene_description` — sirf NAYE background/scene ki tafseel.

    Ahem: is mein product ka hulia bilkul mat likho. Bria product ke asal pixels
    ko composite karta hai; agar prompt product describe karega to woh scene
    mein us cheez ki DOOSRI copy bana sakta hai.
    """
    parts = []

    # User ka custom prompt sabse important — wahi scene ki bunyaad banta hai.
    if form_data.get("custom_prompt"):
        parts.append(form_data["custom_prompt"])

    if form_data.get("mood"):
        parts.append(f"Visual mood: {form_data['mood']}.")

    if form_data.get("occasion") and form_data["occasion"] not in (None, "None"):
        parts.append(f"Occasion theme: {form_data['occasion']}.")

    country = store_country(brand)
    if country:
        parts.append(f"A setting that suits shoppers in {country}.")

    # Koi choice na aaye to bhi scene_description khali nahi ja sakta (Bria par
    # ye required field hai), is liye ek neutral studio fallback.
    if not parts:
        parts.append("A clean, professional studio setting with soft lighting.")

    parts.append("Professional advertising photography with cinematic lighting.")
    parts.append(BOTTOM_CLEAR_GUARDRAIL)
    parts.append(NO_TEXT_GUARDRAIL)

    return " ".join(parts)


def build_model_options(product: dict, form_data: dict, brand=None,
                        width: int = 1024, height: int = 1024) -> dict:
    """
    Claid ka `options` block — pose + background + aspect ratio.

    Claid ke documented options sirf yehi teen hain (pose, background,
    aspect_ratio); model ki demographics ka koi documented field nahi hai, is
    liye market context background mein jata hai.
    """
    # Local import: aspect_ratio_label common.py mein hai, aur common.py kisi
    # prompt_builder ko import nahi karta — module-level import karne se circle
    # nahi banta, lekin ise yahin rakhna is file ko provider-agnostic rakhta hai.
    from modules.ads_generation.services.common import aspect_ratio_label

    background_parts = []

    if form_data.get("custom_prompt"):
        background_parts.append(form_data["custom_prompt"])

    if form_data.get("mood"):
        background_parts.append(f"Visual mood: {form_data['mood']}.")

    if form_data.get("occasion") and form_data["occasion"] not in (None, "None"):
        background_parts.append(f"Occasion theme: {form_data['occasion']}.")

    country = store_country(brand)
    if country:
        background_parts.append(f"A setting that suits shoppers in {country}.")

    if not background_parts:
        background_parts.append("Minimalistic studio background.")

    background_parts.append(BOTTOM_CLEAR_GUARDRAIL)
    background_parts.append(NO_TEXT_GUARDRAIL)

    return {
        # Claid ka apna default pose — standard e-commerce shot, har SKU par
        # consistent rehta hai.
        "pose": "full body, front view, neutral stance, arms relaxed",
        "background": " ".join(background_parts),
        "aspect_ratio": aspect_ratio_label(width, height),
    }


def build_copy_prompt_context(product: dict, form_data: dict, brand=None) -> dict:
    """
    brand = BrandProfile, sirf market context ke liye. Uske baghair ad copy
    prompt ko pata hi nahi chalta ke store kis mulk ka hai — aur pehle wo
    khaali jagah ek hardcoded mulk se bhari hui thi.
    """
    return {
        "product_name": product.get("name", ""),
        "price": product.get("price", ""),
        "description": product.get("description", ""),
        "category": product.get("category", ""),
        "mood": form_data.get("mood", ""),
        "occasion": form_data.get("occasion", ""),
        "cta_goal": form_data.get("cta_goal", ""),
        "brand": brand,
    }