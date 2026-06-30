# basescan_scraper/config.py
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_url: str = Field(default="https://basescan.org", alias="BASESCAN_BASE_URL")
    request_timeout_seconds: float = Field(default=15.0, alias="REQUEST_TIMEOUT_SECONDS")
    max_response_bytes: int = Field(default=20_971_520, alias="MAX_RESPONSE_BYTES")
    fetch_max_retries: int = Field(default=3, alias="FETCH_MAX_RETRIES")
    outbound_min_interval_seconds: float = Field(
        default=0.25, alias="OUTBOUND_MIN_INTERVAL_SECONDS"
    )
    cache_ttl_seconds: int = Field(default=30, alias="CACHE_TTL_SECONDS")
    cache_max_items: int = Field(default=2000, alias="CACHE_MAX_ITEMS")
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_ORIGINS"
    )
    max_page_offset: int = Field(default=100, alias="MAX_PAGE_OFFSET")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
