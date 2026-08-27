import os
import logging
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

logger = logging.getLogger(__name__)

DEFAULT_INSECURE_DEV_SECRET = "hospital-super-secret-key-change-in-production-2026"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore"
    )

    PROJECT_NAME: str = "Multi-Agent Hospital System"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    API_V1_STR: str = "/api/v1"
    
    # Cryptographic Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", DEFAULT_INSECURE_DEV_SECRET)
    ALGORITHM: str = "HS256"
    JWT_SECRET: str = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", DEFAULT_INSECURE_DEV_SECRET))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Configurable CORS Origins
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8000"
    )

    # Database Configuration (PostgreSQL with SQLite async fallback)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite+aiosqlite:///./hospital.db"
    )

    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Optional LLM Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY", None)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Simulation Settings
    ENABLE_LLM_FALLBACK: bool = True
    SIMULATION_TIME_ACCELERATION: float = 1.0  # 1.0 = real-time

    # Production API Docs Configuration
    ENABLE_PROD_DOCS: bool = os.getenv("ENABLE_PROD_DOCS", "false").lower() in ["true", "1", "yes"]

    def get_allowed_origins(self) -> List[str]:
        """Parse comma-delimited ALLOWED_ORIGINS string into a clean list of origins."""
        if not self.ALLOWED_ORIGINS:
            return ["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"]
        origins = [orig.strip() for orig in self.ALLOWED_ORIGINS.split(",") if orig.strip()]
        return origins if origins else ["http://localhost:3000", "http://localhost:5173"]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforces that production deployments do NOT run with default development secrets."""
        if self.ENVIRONMENT.lower() in ["production", "prod"]:
            insecure_secrets = {
                DEFAULT_INSECURE_DEV_SECRET,
                "secret",
                "changeme",
                "password",
                "admin",
                ""
            }
            if not self.SECRET_KEY or self.SECRET_KEY in insecure_secrets or len(self.SECRET_KEY) < 16:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: Production environment detected, but SECRET_KEY "
                    "is insecure, default, or under 16 characters. Set a strong, unique SECRET_KEY environment variable."
                )
            if not self.JWT_SECRET or self.JWT_SECRET in insecure_secrets or len(self.JWT_SECRET) < 16:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: Production environment detected, but JWT_SECRET "
                    "is insecure, default, or under 16 characters. Set a strong, unique JWT_SECRET environment variable."
                )
        return self


settings = Settings()
