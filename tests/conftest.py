import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://chat:chatpass@localhost:5433/chatchat_test",
)
os.environ.setdefault("SECRET_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
