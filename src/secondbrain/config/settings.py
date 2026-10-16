from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """App settings. Override any of them with env vars or a .env file,
    e.g. SECONDBRAIN_DATABASE_URL=."""

    model_config = SettingsConfigDict(env_prefix="SECONDBRAIN_", env_file=".env", extra="ignore")

    database_url: str

    # --- Auth ---
    jwt_secret: str  # generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # --- Email verification (Brevo) ---
    # If brevo_api_key is empty, the verification link is logged instead of emailed (dev mode).
    brevo_api_key: str
    brevo_sender_email: str = ""  # must be a sender/domain verified in Brevo
    brevo_sender_name: str = "Second Brain"

    app_base_url: str = "http://localhost:8000"     # Meaning the backend
    frontend_base_url: str = ""
    verification_token_ttl_hours: int = 24
    password_reset_token_ttl_minutes: int = 30

settings = Settings()
