import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    owner_token: str = os.getenv("STUDIO_OWNER_TOKEN", "")
    workspace_limit: int = int(os.getenv("WORKSPACE_BUDGET_MICRO_USD", "50000000"))
    render_tariff: int = int(os.getenv("RENDER_TARIFF_MICRO_USD", "20000"))
    cors_origin: str = os.getenv("WEB_ORIGIN", "http://localhost:3000")
    data_dir: str = os.getenv("DATA_DIR", "data")
    s3_endpoint: str = os.getenv("R2_ENDPOINT", "")
    s3_bucket: str = os.getenv("R2_BUCKET", "")
    s3_key: str = os.getenv("R2_ACCESS_KEY_ID", "")
    s3_secret: str = os.getenv("R2_SECRET_ACCESS_KEY", "")

settings = Settings()
