import os
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)


class Config:
    APP_NAME = "FinnSpark"
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'finnspark.db')}",
    )
    JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-9f2c1a7e4b")
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
    REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
    MEDIA_DIR = os.getenv(
        "MEDIA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media"),
    )
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
    SUPPORTED_LANGUAGES = ["en", "ar", "ru", "fr", "pt"]

    # SMTP (optional) — when SMTP_HOST is set, invites are emailed directly
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")       # e.g. "finnspark <noreply@finnpact.com>"
    SMTP_TLS = os.getenv("SMTP_TLS", "1") == "1"

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM)


config = Config()
