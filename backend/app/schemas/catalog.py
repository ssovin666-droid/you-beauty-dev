from pydantic import BaseModel, ConfigDict

from app.models.catalog import ShadeGroup


class BrandOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    name: str
    slug: str
    image_url: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    name: str
    variant: str | None = None
    size: str | None = None
    category: str | None = None
    image_url: str | None = None
    shade_group: ShadeGroup | None = None
    brand: BrandOut | None = None


class TrackProductIn(BaseModel):
    product_id: int
    list_type: str


class TrackRecognizedProductIn(BaseModel):
    list_type: str
    brand: str | None = None
    product_name: str
    variant: str | None = None
    size: str | None = None
    category: str | None = None
    # Невалидное значение не ломает сохранение —
    # роут его просто проигнорирует.
    shade_group: str | None = None


class FollowBrandIn(BaseModel):
    name: str
