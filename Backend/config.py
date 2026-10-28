from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    ) # automatically load the below values from our .env file

    secret_key: SecretStr # this type displays *** instead of actual value when printing or logging
    algorithm: str = "HS256" # default value
    access_token_expire_minutes: int = 30 # default value

    max_upload_size_bytes: int = 5 * 1024 * 1024 # 5MB, profile picture uploads larger than this are rejected


settings = Settings()
