from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "You Beauty API"
    database_url: str
    bot_token: str = ""
    bot_username: str = "cosmi_bbot"
    mini_app_url: str = "http://localhost:5173"
    openai_api_key: str = ""
    amplitude_api_key: str = ""
    analytics_enabled: bool = False
    # Публичный https-адрес API (без /api) для ссылок
    # на карточки сторис. Пусто — берём из запроса.
    public_api_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
