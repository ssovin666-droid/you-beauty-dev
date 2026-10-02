from typing import Any

from amplitude import Amplitude, BaseEvent, EventOptions, Identify

from app.core.config import get_settings


settings = get_settings()

_client: Amplitude | None = None


def get_amplitude_client() -> Amplitude | None:
    global _client

    if not settings.amplitude_api_key:
        return None

    if _client is None:
        _client = Amplitude(
            settings.amplitude_api_key
        )

    return _client


def track_event(
    user_id: int | str,
    event_type: str,
    event_properties: dict[str, Any] | None = None,
) -> None:
    client = get_amplitude_client()

    if client is None:
        return

    client.track(
        BaseEvent(
            event_type=event_type,
            user_id=str(user_id),
            event_properties=event_properties,
        )
    )


def set_user_property_once(
    user_id: int | str,
    property_name: str,
    value: Any,
) -> None:
    if value is None:
        return

    client = get_amplitude_client()

    if client is None:
        return

    identify = Identify()

    identify.set_once(
        property_name,
        value,
    )

    client.identify(
        identify,
        EventOptions(
            user_id=str(user_id)
        ),
    )


def flush_amplitude() -> None:
    client = get_amplitude_client()

    if client is None:
        return

    client.flush()
