from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://chat:chatpass@localhost:5433/chatchat"
    redis_url: str = "redis://localhost:6380/0"
    secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "*"
    environment: str = "development"

    rate_limit_auth: str = "10/minute"
    rate_limit_global: str = "100/minute"

    log_format: str = "json"

    ai_provider: str = "mock"

    @property
    def db_dsn(self) -> str:
        return self.database_url

    @property
    def redis_dsn(self) -> str:
        return self.redis_url

    @property
    def is_prod(self) -> bool:
        return self.environment == "production"


settings = Settings()
