import io
import json

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def build_certificate(data: dict) -> tuple[bytes, bytes]:
    """Render the JSON and PDF certificate for an approved log. Returns (json_bytes, pdf_bytes)."""
    json_bytes = json.dumps(data, indent=2, default=str).encode()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 90, "Carbon Sequestration Certificate")
    c.setFont("Helvetica", 12)
    y = h - 150
    lines = [
        ("Certificate ID", data["certificate_id"]),
        ("Farmer", data["farmer_name"]),
        ("Plot", f"{data['plot_name']} ({data['acreage']} acres, {data['crop_type']})"),
        ("Location", f"{data['latitude']:.5f}, {data['longitude']:.5f}"),
        ("Practice", data["practice"]),
        ("Performed on", data["performed_on"]),
        ("Verified by auditor ID", data["verified_by"]),
        ("Evidence files", data.get("evidence_count", 0)),
        ("Methodology", data.get("methodology", "n/a")),
        ("Estimated CO2e", f"{data['co2e_tonnes']} tonnes"),
        ("Farmer payout", f"USD {data['payout_usd']}"),
        ("Issued at", data["issued_at"]),
    ]
    for label, value in lines:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(70, y, f"{label}:")
        c.setFont("Helvetica", 12)
        c.drawString(230, y, str(value))
        y -= 26
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(70, 60, data.get("disclaimer", "Estimate only; not a registry-issued credit."))
    c.save()
    return json_bytes, buf.getvalue()
