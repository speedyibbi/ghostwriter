from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase / PostgREST ──
    supabase_url: str
    supabase_key: str

    # ── Gemini ──
    gemini_api_key: str
    gemini_model: str = "models/gemini-2.5-flash"

    # ── SMTP ──
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_to: str = ""

    # ── Output ──
    output_dir: str = "./output"

    # ── Server ──
    bind_host: str = "127.0.0.1"
    # When set, all /api/* requests must send header X-API-Key with this value.
    api_key: str = ""
    # Reset processing rows older than this many minutes on startup (0 = disabled).
    stale_job_minutes: int = 30

    # ── Google Sheets ──
    google_sheets_credentials_json: str = ""


settings = Settings()
