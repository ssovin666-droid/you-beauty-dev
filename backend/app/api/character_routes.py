import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import ShareCard, User
from app.services.character import (
    CharacterError,
    ack_rewards,
    equip_item,
    evaluate_character,
    mark_shared,
    serialize_character,
    unbox_character,
)
from app.services.telegram_auth import get_current_user


router = APIRouter()

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SHARE_CARD_BYTES = 4 * 1024 * 1024
KEEP_SHARE_CARDS_PER_USER = 3


class EquipIn(BaseModel):
    item_code: str = Field(min_length=1, max_length=64)
    equip: bool = True


class AckRewardsIn(BaseModel):
    reward_ids: list[int] = Field(default_factory=list, max_length=50)


def _raise(exc: CharacterError):
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/character")
def get_character(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    character = evaluate_character(db, current_user)
    return serialize_character(db, current_user, character)


@router.post("/character/unbox")
def post_unbox(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        character = unbox_character(db, current_user)
    except CharacterError as exc:
        _raise(exc)

    return serialize_character(db, current_user, character)


@router.post("/character/equip")
def post_equip(
    payload: EquipIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        equip_item(db, current_user, payload.item_code, payload.equip)
    except CharacterError as exc:
        _raise(exc)

    character = evaluate_character(db, current_user)
    return serialize_character(db, current_user, character)


@router.post("/character/rewards/ack")
def post_ack_rewards(
    payload: AckRewardsIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"ok": True, "acked": ack_rewards(db, current_user, payload.reward_ids)}


@router.post("/character/shared")
def post_shared(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    character = mark_shared(db, current_user)
    return {"ok": True, "shared_at": character.shared_at.isoformat()}


def _public_base_url(request: Request) -> str:
    configured = get_settings().public_api_url.strip()
    if configured:
        return configured.rstrip("/")

    # Railway проксирует https → http; Telegram
    # принимает в shareToStory только https.
    base = str(request.base_url).rstrip("/")
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto.split(",")[0].strip() == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


@router.post("/character/share-card")
async def post_share_card(
    file: UploadFile,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read(MAX_SHARE_CARD_BYTES + 1)

    if len(content) > MAX_SHARE_CARD_BYTES:
        raise HTTPException(status_code=413, detail="Share card is too large")

    if not content.startswith(PNG_SIGNATURE):
        raise HTTPException(status_code=400, detail="Share card must be PNG")

    token = secrets.token_urlsafe(24)
    db.add(ShareCard(token=token, user_id=current_user.id, content=content))
    db.flush()

    # Храним только последние карточки пользователя.
    stale = db.scalars(
        select(ShareCard)
        .where(ShareCard.user_id == current_user.id)
        .order_by(ShareCard.id.desc())
        .offset(KEEP_SHARE_CARDS_PER_USER)
    ).all()
    for row in stale:
        db.delete(row)

    db.commit()

    return {
        "ok": True,
        "url": f"{_public_base_url(request)}/api/share-cards/{token}.png",
    }


@router.get("/share-cards/{token}.png", name="share_card_image")
def get_share_card(
    token: str,
    db: Session = Depends(get_db),
):
    row = db.scalar(select(ShareCard).where(ShareCard.token == token))
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")

    return Response(
        content=row.content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
