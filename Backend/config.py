from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore", # .env is shared with harvest_scripts (API_KEY, BASE_URL), so skip keys not declared here
    ) # automatically load the below values from our .env file

    secret_key: SecretStr # this type displays *** instead of actual value when printing or logging
    algorithm: str = "HS256" # default value
    access_token_expire_minutes: int = 30 # default value

    max_upload_size_bytes: int = 5 * 1024 * 1024 # 5MB, profile picture uploads larger than this are rejected

    # pagination: the page size used when a request doesn't pass ?limit=
    products_per_page: int = 12 # divides evenly into a 2, 3 or 4 column sneaker grid
    items_per_page: int = 10 # cart items, orders and the admin lists
    max_page_size: int = 100 # the largest ?limit= a request may ask for

    reset_token_expire_minutes: int = 60 # how long a password reset link works for

    # email (smtp), the defaults are placeholders, the real values come from .env
    mail_server: str = "localhost"
    mail_port: int = 587
    mail_username: str = ""
    mail_password: SecretStr = SecretStr("")
    mail_from: str = "noreply@example.com"
    mail_use_tls: bool = True # upgrades the connection with STARTTLS, not implicit TLS (port 465)

    # the react app, password reset emails link to <frontend_url>/reset-password?token=...
    frontend_url: str = "http://localhost:5173"


settings = Settings()
