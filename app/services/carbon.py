"""CO2e estimation driven by a methodology file.

The bundled factors (app/data/methodology.json) are ILLUSTRATIVE placeholders, not a certified
methodology such as Verra VM0042. To use real factors, copy that file, edit it with values from
your registry's methodology, and point METHODOLOGY_FILE at it. The methodology name/version is
recorded on every intervention and printed on each certificate.

Schema:
  per_acre_year      {practice: tCO2e per acre per year}  (no_till, cover_crop)
  biochar_per_tonne  tCO2e per tonne of biochar applied
  tree_per_year      tCO2e per tree per year
  buffer_pool_ratio  share (0..1) withheld as a non-permanence buffer, as most registries require
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.models import Practice

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "methodology.json"


@dataclass(frozen=True)
class Methodology:
    name: str
    version: str
    per_acre_year: dict[str, float]
    biochar_per_tonne: float
    tree_per_year: float
    buffer_pool_ratio: float

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"


@lru_cache
def load_methodology() -> Methodology:
    raw = json.loads(Path(settings.methodology_file or DEFAULT_FILE).read_text())
    ratio = float(raw.get("buffer_pool_ratio", 0.0))
    if not 0 <= ratio < 1:
        raise ValueError("buffer_pool_ratio must be in [0, 1)")
    return Methodology(
        name=raw["name"],
        version=str(raw["version"]),
        per_acre_year={k: float(v) for k, v in raw["per_acre_year"].items()},
        biochar_per_tonne=float(raw["biochar_per_tonne"]),
        tree_per_year=float(raw["tree_per_year"]),
        buffer_pool_ratio=ratio,
    )


def estimate_co2e(practice: Practice, acreage: float, quantity: float | None) -> float:
    """Net creditable tCO2e after the methodology's buffer-pool deduction."""
    m = load_methodology()
    if practice.value in m.per_acre_year:
        value = m.per_acre_year[practice.value] * acreage
    elif practice == Practice.biochar:
        value = m.biochar_per_tonne * (quantity or 0)
    elif practice == Practice.tree_planting:
        value = m.tree_per_year * (quantity or 0)
    else:
        raise ValueError(f"Unknown practice {practice}")
    return round(value * (1 - m.buffer_pool_ratio), 4)


def payout_usd(co2e_tonnes: float) -> float:
    return round(co2e_tonnes * settings.credit_price_usd * settings.farmer_share, 2)
