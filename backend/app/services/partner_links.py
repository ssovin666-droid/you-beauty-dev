from urllib.parse import unquote_plus, urlsplit, urlunsplit


def with_telegram_sub1(url: str, telegram_user_id: int) -> str:
    """Set the outer tracking parameter without re-encoding the partner deeplink."""
    parts = urlsplit(url)
    query = [
        parameter
        for parameter in parts.query.split("&")
        if parameter
        and unquote_plus(parameter.split("=", 1)[0]) != "sub1"
    ]
    query.append(f"sub1={telegram_user_id}")
    return urlunsplit(parts._replace(query="&".join(query)))
