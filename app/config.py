from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # "production" enables startup safety checks
    database_url: str = "postgresql+psycopg2://carbon:carbon@localhost:5432/carbon"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = DEFAULT_SECRET
    access_token_minutes: int = 60
    nasa_power_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"

    # Schema management: dev/tests create tables on startup; production runs `alembic upgrade head`.
    auto_create_schema: bool = True

    # Browser origins allowed to call the API (the Vite dev server by default)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # File storage for certificates and evidence: "local" (directory) or "s3" (S3 / MinIO / R2 ...)
    storage_backend: str = "local"
    certificates_dir: str = "./certificates"  # root directory for the local backend
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # set for MinIO / Cloudflare R2 etc.
    s3_region: str | None = None
    s3_prefix: str = ""

    # Evidence uploads
    max_evidence_mb: int = 10
    evidence_content_types: list[str] = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
    require_evidence_for_approval: bool = False

    # Carbon methodology (JSON file with factors; see app/data/methodology.json)
    methodology_file: str | None = None

    # Plot overlap detection: reject when shared area exceeds this share of the smaller plot
    max_plot_overlap_ratio: float = 0.05
    # Reject polygons whose measured area differs from the declared acreage by more than this ratio (0 disables)
    max_acreage_mismatch_ratio: float = 0.5

    # Satellite verification (Sentinel-2 L2A via a STAC API; no key needed for Earth Search)
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    ndvi_max_cloud_cover: float = 30.0

    # Rate limiting (in-memory, per process)
    rate_limit_login_per_minute: int = 10
    rate_limit_password_per_minute: int = 5

    # Bootstrap admin created on startup if no users exist
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "admin12345"

    # Payout assumptions (illustrative)
    credit_price_usd: float = 15.0
    farmer_share: float = 0.70


settings = Settings()
