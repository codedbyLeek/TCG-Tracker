from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str

    # External APIs
    SCRYDEX_API_KEY: str
    SCRYDEX_TEAM_ID: str

    # App
    ENVIRONMENT: str = "development"


settings = Settings()
