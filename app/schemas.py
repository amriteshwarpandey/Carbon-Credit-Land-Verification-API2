from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import LogStatus, Practice, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    role: Role


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, description="Admin password reset")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class FarmerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    village: str | None = None


class FarmerOut(ORM):
    id: int
    name: str
    phone: str | None
    village: str | None
    created_by_id: int


class PlotCreate(BaseModel):
    name: str
    crop_type: str
    acreage: float = Field(gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geojson: dict | None = Field(default=None, description="GeoJSON Polygon/Point geometry")

    @model_validator(mode="after")
    def resolve_location(self):
        """Accept lat/lon, a GeoJSON geometry, or both. Derive lat/lon from GeoJSON when absent."""
        if self.geojson is not None:
            coords = _flatten_coords(self.geojson)
            if not coords:
                raise ValueError("geojson must be a Point or Polygon geometry with coordinates")
            if self.latitude is None or self.longitude is None:
                self.longitude = sum(c[0] for c in coords) / len(coords)
                self.latitude = sum(c[1] for c in coords) / len(coords)
        if self.latitude is None or self.longitude is None:
            raise ValueError("Provide latitude/longitude or a geojson geometry")
        return self


def _flatten_coords(geom: dict) -> list[list[float]]:
    t, c = geom.get("type"), geom.get("coordinates")
    try:
        if t == "Point":
            return [[float(c[0]), float(c[1])]]
        if t == "Polygon":
            return [[float(p[0]), float(p[1])] for p in c[0]]
    except (TypeError, IndexError, ValueError):
        pass
    return []


class PlotOut(ORM):
    id: int
    farmer_id: int
    name: str
    crop_type: str
    acreage: float
    latitude: float
    longitude: float
    geojson: dict | None


class InterventionCreate(BaseModel):
    practice: Practice
    quantity: float | None = Field(default=None, gt=0, description="Tonnes of biochar, or number of trees")
    performed_on: date
    notes: str | None = None

    @model_validator(mode="after")
    def quantity_required(self):
        if self.practice in (Practice.biochar, Practice.tree_planting) and self.quantity is None:
            raise ValueError(f"quantity is required for {self.practice.value}")
        return self


class ReviewIn(BaseModel):
    notes: str | None = None


class InterventionOut(ORM):
    id: int
    plot_id: int
    practice: Practice
    quantity: float | None
    performed_on: date
    notes: str | None
    status: LogStatus
    submitted_by_id: int
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    review_notes: str | None
    co2e_tonnes: float | None
    methodology: str | None
    processed_at: datetime | None
    evidence_count: int = 0


class EvidenceOut(ORM):
    id: int
    intervention_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by_id: int
    created_at: datetime


class LedgerOut(ORM):
    id: int
    farmer_id: int
    intervention_id: int
    co2e_tonnes: float
    amount_usd: float
    status: str
    created_at: datetime


class FarmerLedger(BaseModel):
    farmer_id: int
    total_co2e_tonnes: float
    total_amount_usd: float
    entries: list[LedgerOut]
