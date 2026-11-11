import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.models import Evidence, InterventionLog, LogStatus, Role, User, utcnow
from app.routers.plots import get_plot_for
from app.schemas import EvidenceOut, InterventionOut, ReviewIn
from app.security import get_current_user, require_roles
from app.services.ndvi import NdviError, ndvi_change
from app.services.storage import StorageError, get_storage
from app.tasks import process_approved_intervention

router = APIRouter(prefix="/interventions", tags=["interventions"])


def _log_for(db: Session, log_id: int, user: User) -> InterventionLog:
    """Fetch a log the user may see (404 for agents who don't own the farmer)."""
    item = db.get(InterventionLog, log_id)
    if not item:
        raise HTTPException(404, "Intervention not found")
    get_plot_for(db, item.plot_id, user)
    return item


def _pending_or_409(db: Session, log_id: int) -> InterventionLog:
    item = db.get(InterventionLog, log_id)
    if not item:
        raise HTTPException(404, "Intervention not found")
    if item.status != LogStatus.pending:
        raise HTTPException(409, f"Already {item.status.value}")
    return item


@router.get("", response_model=list[InterventionOut])
def list_interventions(
    status: LogStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.auditor, Role.admin)),
):
    q = select(InterventionLog).options(selectinload(InterventionLog.evidence)).order_by(InterventionLog.id)
    if status:
        q = q.where(InterventionLog.status == status)
    return db.scalars(q).all()


@router.post("/{log_id}/approve", response_model=InterventionOut)
def approve(
    log_id: int,
    body: ReviewIn | None = None,
    db: Session = Depends(get_db),
    auditor: User = Depends(require_roles(Role.auditor)),
):
    item = _pending_or_409(db, log_id)
    if settings.require_evidence_for_approval and not item.evidence:
        raise HTTPException(422, "Evidence is required: attach at least one file before approval")
    item.status, item.reviewed_by_id, item.reviewed_at = LogStatus.approved, auditor.id, utcnow()
    item.review_notes = body.notes if body else None
    db.commit()
    # Enqueue only after commit so the worker is guaranteed to see the approved row.
    process_approved_intervention.delay(item.id)
    return item


@router.post("/{log_id}/reject", response_model=InterventionOut)
def reject(
    log_id: int,
    body: ReviewIn | None = None,
    db: Session = Depends(get_db),
    auditor: User = Depends(require_roles(Role.auditor)),
):
    item = _pending_or_409(db, log_id)
    item.status, item.reviewed_by_id, item.reviewed_at = LogStatus.rejected, auditor.id, utcnow()
    item.review_notes = body.notes if body else None
    db.commit()
    return item


@router.get("/{log_id}/certificate")
def certificate(log_id: int, format: str = "pdf", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if format not in ("pdf", "json"):
        raise HTTPException(422, "format must be pdf or json")
    item = _log_for(db, log_id, user)
    key = item.certificate_pdf_path if format == "pdf" else item.certificate_json_path
    if not key:
        raise HTTPException(409, "Certificate not generated yet (log not approved, or still processing)")
    try:
        data = get_storage().get(key)
    except StorageError as exc:
        raise HTTPException(404, str(exc))
    return Response(data, media_type="application/pdf" if format == "pdf" else "application/json")


# ---- Evidence ---------------------------------------------------------------------------------

def _safe_name(name: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "file").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:120] or "file"


@router.post("/{log_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    log_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.field_agent, Role.admin)),
):
    item = _log_for(db, log_id, user)
    if item.status != LogStatus.pending:
        raise HTTPException(409, f"Evidence can only be added while the log is pending (it is {item.status.value})")
    if file.content_type not in settings.evidence_content_types:
        raise HTTPException(415, f"Unsupported file type; allowed: {', '.join(settings.evidence_content_types)}")
    limit = settings.max_evidence_mb * 1024 * 1024
    data = await file.read(limit + 1)  # never buffer more than limit+1 bytes
    if len(data) > limit:
        raise HTTPException(413, f"File larger than {settings.max_evidence_mb} MB")
    if not data:
        raise HTTPException(422, "Empty file")

    digest = hashlib.sha256(data).hexdigest()
    ev = Evidence(
        intervention_id=item.id,
        filename=_safe_name(file.filename),
        content_type=file.content_type,
        size_bytes=len(data),
        sha256=digest,
        storage_key="",
        uploaded_by_id=user.id,
    )
    db.add(ev)
    db.flush()  # assign id so the storage key is unique
    ev.storage_key = f"evidence/{item.id}/{ev.id}_{ev.filename}"
    try:
        get_storage().put(ev.storage_key, data, ev.content_type)
    except Exception:
        db.rollback()
        raise HTTPException(502, "Could not store the file")
    db.commit()
    return ev


@router.get("/{log_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(log_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _log_for(db, log_id, user).evidence


@router.get("/{log_id}/evidence/{evidence_id}")
def download_evidence(log_id: int, evidence_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = _log_for(db, log_id, user)
    ev = next((e for e in item.evidence if e.id == evidence_id), None)
    if not ev:
        raise HTTPException(404, "Evidence not found")
    try:
        data = get_storage().get(ev.storage_key)
    except StorageError as exc:
        raise HTTPException(404, str(exc))
    return Response(
        data,
        media_type=ev.content_type,
        headers={"Content-Disposition": f'inline; filename="{ev.filename}"', "X-Content-Type-Options": "nosniff"},
    )


# ---- Satellite verification -------------------------------------------------------------------

@router.get("/{log_id}/ndvi")
def satellite_ndvi(log_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """NDVI before vs after the practice (Sentinel-2). A verification signal, not proof of sequestration."""
    item = _log_for(db, log_id, user)
    plot = item.plot
    try:
        return ndvi_change(plot.geojson, plot.latitude, plot.longitude, plot.acreage, item.performed_on)
    except NdviError as exc:
        raise HTTPException(502, str(exc))
