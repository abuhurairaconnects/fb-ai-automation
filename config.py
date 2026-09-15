import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_CHAT_ID: str = ""  # Telegram User ID to receive post previews & alerts

    # Facebook Meta Graph API & Webhooks
    FB_PAGE_ID: str = ""
    FB_PAGE_ACCESS_TOKEN: str = ""
    FB_VERIFY_TOKEN: str = "my_custom_fb_verify_token_123"  # Challenge token for webhook setup
    FB_APP_SECRET: str = ""

    # YouTube Monitoring
    YOUTUBE_CHANNEL_ID: str = ""  # UC... format or channel handle
    YOUTUBE_CHECK_INTERVAL_MINUTES: int = 30

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
