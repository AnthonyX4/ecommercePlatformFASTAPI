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

    # pagination: the page size used when a request doesn't pass ?limit=
    products_per_page: int = 12 # divides evenly into a 2, 3 or 4 column sneaker grid
    items_per_page: int = 10 # cart items, orders and the admin lists
    max_page_size: int = 100 # the largest ?limit= a request may ask for


settings = Settings()
