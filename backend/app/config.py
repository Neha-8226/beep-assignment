"""Centralized Application Configuration.

Reads environment variables from system environment and optional .env file.
Follows 12-factor application methodology; no hardcoded secrets.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for backend services and pipelines."""

    # Environment
    ENV: str = "development"
    DEBUG: bool = False

    # Database
    # Default to local SQLite; override with Supabase PostgreSQL in production
    DATABASE_URL: str = "sqlite:///./jobs.db"

    # AI / LLM Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_TEMPERATURE: float = 0.0

    # Request Pacing & Rate Limits
    # Note: Actual RPM, TPM, and RPD limits depend on the specific project plan in Google AI Studio.
    GEMINI_REQUEST_DELAY_SECONDS: float = 4.0
    GEMINI_MAX_RETRIES: int = 4
    GEMINI_BASE_RETRY_DELAY: float = 2.0

    # Text Truncation Limit
    CLASSIFIER_DESCRIPTION_MAX_CHARS: int = 3000

    # Pricing Configuration (Configurable; defaults to current standard published rates)
    # Free tier actual cost is $0.00; nominal cost is calculated for economic comparison.
    GEMINI_PRICING_TIER: str = "free"  # 'free' or 'paid'
    GEMINI_INPUT_PRICE_PER_1M: float = 0.30   # $0.30 per 1M prompt tokens
    GEMINI_OUTPUT_PRICE_PER_1M: float = 2.50  # $2.50 per 1M candidate tokens

    # Data Ingestion Source Credentials (free-tier developer keys)
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    JOOBLE_API_KEY: str = ""

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "*",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
