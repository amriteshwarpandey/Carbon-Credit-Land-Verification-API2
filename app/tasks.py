import logging

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import InterventionLog, LedgerEntry, LogStatus, utcnow
from app.services.carbon import estimate_co2e, load_methodology, payout_usd
from app.services.certificate import build_certificate
from app.services.storage import get_storage

log = logging.getLogger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_approved_intervention(self, intervention_id: int) -> dict:
    """Compute CO2e, store certificate files, credit the farmer's ledger.

    Idempotent: a redelivered/retried task will not double-credit the farmer.
    """
    db = SessionLocal()
    try:
        item = db.get(InterventionLog, intervention_id)
        if item is None or item.status != LogStatus.approved:
            log.warning("Intervention %s missing or not approved; skipping", intervention_id)
            return {"skipped": True}
        if db.query(LedgerEntry).filter_by(intervention_id=item.id).first():
            return {"skipped": True, "reason": "already processed"}

        plot, farmer = item.plot, item.plot.farmer
        method = load_methodology()
        co2e = estimate_co2e(item.practice, plot.acreage, item.quantity)
        amount = payout_usd(co2e)
        now = utcnow()

        json_bytes, pdf_bytes = build_certificate(
            {
                "certificate_id": f"CC-{item.id:06d}",
                "intervention_id": item.id,
                "farmer_name": farmer.name,
                "plot_name": plot.name,
                "crop_type": plot.crop_type,
                "acreage": plot.acreage,
                "latitude": plot.latitude,
                "longitude": plot.longitude,
                "practice": item.practice.value,
                "performed_on": item.performed_on.isoformat(),
                "verified_by": item.reviewed_by_id,
                "evidence_count": len(item.evidence),
                "methodology": method.label,
                "buffer_pool_ratio": method.buffer_pool_ratio,
                "co2e_tonnes": co2e,
                "payout_usd": amount,
                "issued_at": now.isoformat(),
                "disclaimer": "Estimate only; not a registry-issued credit."
                if method.name.startswith("ILLUSTRATIVE")
                else f"Estimated using {method.label}; not a registry-issued credit until registered.",
            }
        )
        storage = get_storage()
        json_key, pdf_key = f"certificates/certificate_{item.id}.json", f"certificates/certificate_{item.id}.pdf"
        storage.put(json_key, json_bytes, "application/json")
        storage.put(pdf_key, pdf_bytes, "application/pdf")

        item.co2e_tonnes, item.processed_at, item.methodology = co2e, now, method.label
        item.certificate_json_path, item.certificate_pdf_path = json_key, pdf_key
        db.add(LedgerEntry(farmer_id=farmer.id, intervention_id=item.id, co2e_tonnes=co2e, amount_usd=amount))
        db.commit()
        return {"intervention_id": item.id, "co2e_tonnes": co2e, "amount_usd": amount}
    finally:
        db.close()
