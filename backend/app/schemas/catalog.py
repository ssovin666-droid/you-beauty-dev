from pydantic import BaseModel, ConfigDict


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
