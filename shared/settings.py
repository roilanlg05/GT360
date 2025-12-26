from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class BaseAppSettings(BaseSettings):
    BASE_URL: str = "http://192.168.0.133:3000"
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
        "/v1/auth/verify-data"
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = BaseAppSettings()