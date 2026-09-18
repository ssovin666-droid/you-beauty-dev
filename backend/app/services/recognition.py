from dataclasses import dataclass


@dataclass
class RecognitionResult:
    brand: str
    product_name: str
    variant: str | None = None
    size: str | None = None
    category: str | None = None
    confidence: float = 0.0


async def recognize_product_image(image_bytes: bytes, filename: str | None = None) -> RecognitionResult:
    """Phase 1 contract for AI recognition.

    The OpenAI/Vision provider is deliberately isolated behind this service so the
    rest of the product is not coupled to one model or API implementation.
    """
    raise NotImplementedError("AI recognition provider will be connected in the next milestone")
