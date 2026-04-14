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

    # ── Google Sheets ──
    google_sheets_credentials_json: str = ""


settings = Settings()
