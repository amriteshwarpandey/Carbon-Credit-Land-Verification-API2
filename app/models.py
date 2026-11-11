import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    field_agent = "field_agent"
    auditor = "auditor"
    admin = "admin"


class Practice(str, enum.Enum):
    biochar = "biochar"
    no_till = "no_till"
    tree_planting = "tree_planting"
    cover_crop = "cover_crop"


class LogStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def _enum(e):
    return Enum(e, native_enum=False, length=32)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role))
    is_active: Mapped[bool] = mapped_column(default=True)


class Farmer(Base):
    __tablename__ = "farmers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    village: Mapped[str | None] = mapped_column(String(120))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    plots: Mapped[list["LandPlot"]] = relationship(back_populates="farmer", cascade="all, delete-orphan")


class LandPlot(Base):
    __tablename__ = "land_plots"
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    crop_type: Mapped[str] = mapped_column(String(60))
    acreage: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geojson: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farmer: Mapped[Farmer] = relationship(back_populates="plots")
    logs: Mapped[list["InterventionLog"]] = relationship(back_populates="plot", cascade="all, delete-orphan")


class InterventionLog(Base):
    __tablename__ = "intervention_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    plot_id: Mapped[int] = mapped_column(ForeignKey("land_plots.id"), index=True)
    practice: Mapped[Practice] = mapped_column(_enum(Practice))
    quantity: Mapped[float | None] = mapped_column(Float)  # tonnes of biochar / number of trees
    performed_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LogStatus] = mapped_column(_enum(LogStatus), default=LogStatus.pending, index=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    # Populated by the background pipeline
    co2e_tonnes: Mapped[float | None] = mapped_column(Float)
    certificate_json_path: Mapped[str | None] = mapped_column(String(255))
    certificate_pdf_path: Mapped[str | None] = mapped_column(String(255))
    methodology: Mapped[str | None] = mapped_column(String(120))  # "<name> <version>" used for the estimate
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    plot: Mapped[LandPlot] = relationship(back_populates="logs")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="intervention", cascade="all, delete-orphan")

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("intervention_id", name="uq_ledger_intervention"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("intervention_logs.id"))
    co2e_tonnes: Mapped[float] = mapped_column(Float)
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending -> paid
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    """A file (photo, receipt, PDF) attached to an intervention so an auditor can verify it."""

    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("intervention_logs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    intervention: Mapped[InterventionLog] = relationship(back_populates="evidence")
