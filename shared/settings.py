from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class BaseAppSettings(BaseSettings):
    BASE_URL: str = "https://dev.gt360.app"
    BACKEND_URL: str = "http://app:8000"

    # File uploads configuration
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/var/www/gt360/uploads")
    UPLOAD_BASE_URL: str = os.getenv("UPLOAD_BASE_URL", "https://api.gt360.app/uploads")
    MAX_UPLOAD_SIZE: int = 4 * 1024 * 1024  # 4 MB
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD")
    BREVO_KEY: Optional[str] = os.getenv("BREVO_KEY")
    TOKEN_DURATION: str = os.getenv("TOKEN_DURATION")
    JWT_SECRET_KEY: Optional[str] = os.getenv("JWT_SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM")
    PEPPER: Optional[str] = os.getenv("PEPPER")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET")
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    AIRLABS_API_KEY: Optional[str] = os.getenv("AIRLABS_API_KEY")
    PUBLIC_PATHS: list[str] = [
        "/v1/auth/register",
        "/v1/auth/sign-in",
        "/v1/auth/refresh",
        "/v1/auth/verify-email",
        "/v1/auth/forgot-password",
        "/v1/auth/reset-password",
        "/docs",
        "/redoc",
        "/favicon.ico",
        "/openapi.json",
        "/v1/auth/register/organization",
        "/health",
        "/ready",
        "/v1/auth/verify-data",
        "/v1/webhooks/trips",
        "/v1/webhooks/flights",  # AeroDataBox push notifications
        "/v1/crew-lookup/config",  # QR code config (public)
        "/v1/crew-lookup/health",  # QR code health check (public)
        "/v1/trips/search/qr",  # QR code trip search (public)
        "/v1/support/contact",  # Support contact form (public)
        "/uploads",  # Static file uploads (public)
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = BaseAppSettings()