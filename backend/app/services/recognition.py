import base64
import json
import mimetypes
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class RecognitionResult:
    brand: str | None
    product_name: str | None
    variant: str | None = None
    size: str | None = None
    category: str | None = None
    confidence: float = 0.0
    shade_group: str | None = None


SHADE_GROUPS = (
    "bold",
    "goth",
    "nude",
    "pastel",
    "glow",
    "glitter",
)


def _get_output_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")

    return ""


async def recognize_product_image(
    image_bytes: bytes,
    filename: str | None = None,
) -> RecognitionResult:
    settings = get_settings()

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    media_type = mimetypes.guess_type(filename or "")[0] or "image/jpeg"
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    schema = {
        "type": "object",
        "properties": {
            "brand": {
                "type": ["string", "null"],
            },
            "product_name": {
                "type": ["string", "null"],
            },
            "variant": {
                "type": ["string", "null"],
            },
            "size": {
                "type": ["string", "null"],
            },
            "category": {
                "type": ["string", "null"],
            },
            "shade_group": {
                "type": ["string", "null"],
                "enum": [*SHADE_GROUPS, None],
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
        "required": [
            "brand",
            "product_name",
            "variant",
            "size",
            "category",
            "shade_group",
            "confidence",
        ],
        "additionalProperties": False,
    }

    payload = {
        "model": "gpt-5.6-luna",
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Identify the exact cosmetic product shown in the image. "
                            "Read visible packaging text carefully. "
                            "Return the brand, exact product name, variant or shade if visible, "
                            "size or volume if visible, and product category. "
                            "Do not invent information that is not visible or reasonably identifiable. "
                            "If uncertain, use null for that field and lower confidence. "
                            "Also classify the product aesthetic as shade_group: "
                            "bold — bright saturated colors (red lipstick, neon, bright liner); "
                            "goth — dark or vampy shades (black liner, plum, burgundy, dark nails); "
                            "nude — natural skin-like shades (foundation, concealer, beige, brown, peach); "
                            "pastel — soft light pinks, lilac, baby blue, cute girly shades; "
                            "glow — skincare and glow products (serum, cream, toner, SPF, highlighter without glitter); "
                            "glitter — glitter, shimmer, sparkle, metallic or holographic finish. "
                            "Use null if the aesthetic is not clear."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": (
                            f"data:{media_type};base64,{image_base64}"
                        ),
                        "detail": "high",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "cosmetic_product_recognition",
                "strict": True,
                "schema": schema,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI API error {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()
    output_text = _get_output_text(data)

    if not output_text:
        raise RuntimeError("OpenAI returned no recognition result")

    parsed = json.loads(output_text)

    return RecognitionResult(
        brand=parsed.get("brand"),
        product_name=parsed.get("product_name"),
        variant=parsed.get("variant"),
        size=parsed.get("size"),
        category=parsed.get("category"),
        confidence=float(parsed.get("confidence", 0)),
        shade_group=(
            parsed.get("shade_group")
            if parsed.get("shade_group") in SHADE_GROUPS
            else None
        ),
    )
