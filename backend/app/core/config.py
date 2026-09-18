from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "You Beauty API"
    database_url: str
    bot_token: str = ""
    bot_username: str = "you_beauty_bot"
    mini_app_url: str = "http://localhost:5173"
    openai_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
