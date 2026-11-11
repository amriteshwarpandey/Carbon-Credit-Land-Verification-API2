from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import DEFAULT_SECRET, settings
from app.db import Base, SessionLocal, engine
from app.models import Role, User
from app.routers import auth, farmers, interventions, plots
from app.security import hash_password


def check_production_settings() -> None:
    if settings.environment.lower() != "production":
        return
    problems = []
    if settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a random value of at least 32 characters")
    if settings.bootstrap_admin_password == "admin12345":
        problems.append("BOOTSTRAP_ADMIN_PASSWORD must be changed from the default")
    if settings.auto_create_schema:
        problems.append("set AUTO_CREATE_SCHEMA=false and run `alembic upgrade head` instead")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_production_settings()
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)  # dev/test convenience; production uses Alembic migrations
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is None:
            db.add(
                User(
                    email=settings.bootstrap_admin_email,
                    full_name="Bootstrap Admin",
                    role=Role.admin,
                    hashed_password=hash_password(settings.bootstrap_admin_password),
                )
            )
            db.commit()
    yield


app = FastAPI(title="Smallholder Carbon Credit & Land Verification API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(farmers.router)
app.include_router(plots.router)
app.include_router(interventions.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
