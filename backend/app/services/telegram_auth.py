import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException


BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram initData считаем свежими в течение суток.
MAX_AUTH_AGE_SECONDS = 60 * 60 * 24


def get_telegram_user_id(
    x_telegram_init_data: str = Header(
        default="",
        alias="X-Telegram-Init-Data",
    ),
) -> int:
    if not BOT_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="BOT_TOKEN is not configured",
        )

    if not x_telegram_init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram authorization required",
        )

    try:
        data = dict(
            parse_qsl(
                x_telegram_init_data,
                keep_blank_values=True,
            )
        )

        received_hash = data.pop("hash", None)

        if not received_hash:
            raise HTTPException(
                status_code=401,
                detail="Telegram hash is missing",
            )

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
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

        auth_date = int(
            data.get("auth_date", "0")
        )

        if not auth_date:
            raise HTTPException(
                status_code=401,
                detail="Telegram auth_date is missing",
            )

        if (
            time.time() - auth_date
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

        user = json.loads(user_raw)

        telegram_user_id = int(
            user["id"]
        )

        return telegram_user_id

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Telegram authorization: {exc}",
        )
