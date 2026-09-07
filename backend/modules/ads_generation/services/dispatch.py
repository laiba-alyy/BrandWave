"""
generation_mode -> base-image provider.

Naya mode add karne ke liye sirf do cheezein: service mein wahi signature wala
function likho, aur us ka entry yahan daal do. routes.py ko chhoona nahi parta.

    generate_*(product, form_data, brand, width, height) -> str  # local path
"""
from modules.ads_generation.services.bria_service import generate_scene_image
from modules.ads_generation.services.claid_service import generate_on_model_image
from modules.ads_generation.services.common import AdImageServiceError

# Key = generation_mode jo frontend bhejta hai.
BASE_IMAGE_GENERATORS = {
    "scene": generate_scene_image,        # Bria  — product/model pehle se photo mein
    "on_model": generate_on_model_image,  # Claid — flat garment ko model par pehnao
}

DEFAULT_MODE = "scene"

# Mode -> woh naam jo user ko error mein dikhe.
MODE_LABELS = {
    "scene": "Change scene",
    "on_model": "Put on a model",
}


def generate_base_image(mode: str, product: dict, form_data: dict, brand,
                        width: int, height: int) -> str:
    """
    Chune hue mode ka provider chalao aur base image ka local path do.

    Text yahan NAHI lagta — woh image_polish.add_text_overlay ka kaam hai, jo
    is ke baad chalta hai (Pillow), bilkul pehle ki tarah.
    """
    generator = BASE_IMAGE_GENERATORS.get(mode)
    if generator is None:
        raise AdImageServiceError(
            f"Unknown generation mode '{mode}'. "
            f"Choose one of: {', '.join(sorted(BASE_IMAGE_GENERATORS))}.",
            detail=f"mode={mode!r} not in registry",
        )
    return generator(product, form_data, brand, width, height)
