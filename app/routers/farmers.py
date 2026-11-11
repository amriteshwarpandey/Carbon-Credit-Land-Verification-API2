from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Farmer, LedgerEntry, Role, User
from app.schemas import FarmerCreate, FarmerLedger, FarmerOut
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/farmers", tags=["farmers"])


def get_farmer_for(db: Session, farmer_id: int, user: User) -> Farmer:
    """Field agents only see farmers they onboarded; auditors/admins see all."""
    farmer = db.get(Farmer, farmer_id)
    if not farmer or (user.role == Role.field_agent and farmer.created_by_id != user.id):
        raise HTTPException(404, "Farmer not found")
    return farmer


@router.post("", response_model=FarmerOut, status_code=201)
def onboard_farmer(
    body: FarmerCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.field_agent, Role.admin))
):
    farmer = Farmer(**body.model_dump(), created_by_id=user.id)
    db.add(farmer)
    db.commit()
    return farmer


@router.get("", response_model=list[FarmerOut])
def list_farmers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Farmer).order_by(Farmer.id)
    if user.role == Role.field_agent:
        q = q.where(Farmer.created_by_id == user.id)
    return db.scalars(q).all()


@router.get("/{farmer_id}", response_model=FarmerOut)
def get_farmer(farmer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_farmer_for(db, farmer_id, user)


@router.get("/{farmer_id}/ledger", response_model=FarmerLedger)
def farmer_ledger(farmer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_farmer_for(db, farmer_id, user)
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.farmer_id == farmer_id).order_by(LedgerEntry.id)).all()
    return FarmerLedger(
        farmer_id=farmer_id,
        total_co2e_tonnes=round(sum(e.co2e_tonnes for e in entries), 4),
        total_amount_usd=round(sum(e.amount_usd for e in entries), 2),
        entries=entries,
    )
