import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User


MAX_AUTH_AGE_SECONDS = 60 * 60 * 24


@dataclass
class TelegramAccount:
    telegram_user_id: int
    username: str | None
    first_name: str | None


def validate_telegram_init_data(
    init_data: str,
) -> TelegramAccount:
    bot_token = os.getenv("BOT_TOKEN", "")

    if not bot_token:
        raise HTTPException(
            status_code=500,
            detail="BOT_TOKEN is not configured",
        )

    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram authorization required",
        )

    try:
        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True,
            )
        )

        received_hash = data.pop(
            "hash",
            None,
        )

        if not received_hash:
            raise HTTPException(
                status_code=401,
                detail="Telegram hash is missing",
            )

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value
            in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid Telegram signature",
            )

        auth_date_raw = data.get(
            "auth_date"
        )

        if not auth_date_raw:
            raise HTTPException(
                status_code=401,
                detail="Telegram auth_date is missing",
            )

        auth_date = int(auth_date_raw)
        now = int(time.time())

        if (
            now - auth_date
            > MAX_AUTH_AGE_SECONDS
        ):
            raise HTTPException(
                status_code=401,
                detail="Telegram authorization expired",
            )

        user_raw = data.get("user")

        if not user_raw:
            raise HTTPException(
                status_code=401,
                detail="Telegram user is missing",
            )

        user_data = json.loads(
            user_raw
        )

        telegram_user_id = int(
            user_data["id"]
        )

        username = user_data.get(
            "username"
        )

        first_name = user_data.get(
            "first_name"
        )

        return TelegramAccount(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid Telegram authorization: "
                f"{exc}"
            ),
        )


def get_current_user(
    x_telegram_init_data: str = Header(
        default="",
        alias="X-Telegram-Init-Data",
    ),
    db: Session = Depends(get_db),
) -> User:
    telegram_account = (
        validate_telegram_init_data(
            x_telegram_init_data
        )
    )

    user = db.scalar(
        select(User).where(
            User.telegram_user_id
            == telegram_account.telegram_user_id
        )
    )

    if user:
        changed = False

        if (
            user.username
            != telegram_account.username
        ):
            user.username = (
                telegram_account.username
            )
            changed = True

        if (
            user.first_name
            != telegram_account.first_name
        ):
            user.first_name = (
                telegram_account.first_name
            )
            changed = True

        if changed:
            db.commit()
            db.refresh(user)

        return user

    user = User(
        telegram_user_id=(
            telegram_account.telegram_user_id
        ),
        username=telegram_account.username,
        first_name=telegram_account.first_name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
