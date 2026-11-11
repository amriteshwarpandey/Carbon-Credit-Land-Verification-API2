# Smallholder Carbon Credit & Land Verification API

FastAPI + PostgreSQL + Celery/Redis backend modelling the regenerative-agriculture carbon credit workflow.

```
Field Agent ──onboards──▶ Farmer ─▶ LandPlot ─▶ InterventionLog (pending)
Auditor ──approve──▶ status=approved ──▶ Celery task:
                       ├─ estimate CO2e (acreage × practice factor)
                       ├─ write PDF + JSON certificate
                       └─ credit farmer's payout ledger (idempotent)
```

## Run
```bash
docker compose up --build        # api :8000, worker, postgres, redis
# docs: http://localhost:8000/docs   (bootstrap admin: admin@example.com / admin12345)
```
Local tests (no Docker needed – SQLite + eager Celery): `pip install -r requirements.txt && pytest`

## Frontend
React + Vite (plain JS) in `frontend/`. Dev server proxies `/api` to the API on :8000.
```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```
Set `VITE_API_URL` for a production build pointing at a deployed API (and add its origin to `CORS_ORIGINS`).

## Roles
| Role | Can |
|---|---|
| `admin` | create users, everything agents can do, view all |
| `field_agent` | onboard farmers, register plots, log interventions (only for own farmers) |
| `auditor` | list/approve/reject logs, read all farmers/plots/ledgers |

## Endpoints
- `POST /auth/login` (form: username=email, password) · `GET /auth/me` · `POST /users` (admin)
- `POST/GET /farmers` · `GET /farmers/{id}` · `GET /farmers/{id}/ledger`
- `POST/GET /farmers/{id}/plots` · `GET /plots/{id}` (plot takes lat/lon and/or GeoJSON; centroid is derived)
- `GET /plots/{id}/weather?start=&end=` – NASA POWER rainfall, temperature, root-zone soil wetness
- `POST /plots/{id}/interventions` · `GET /interventions?status=pending`
- `POST /interventions/{id}/approve|reject` · `GET /interventions/{id}/certificate?format=pdf|json`

- `GET /users` · `PATCH /users/{id}` (admin: edit role/name, deactivate, reset password) · `POST /auth/change-password`
- `POST/GET /interventions/{id}/evidence` · `GET /interventions/{id}/evidence/{eid}` (photo/PDF, 10 MB, sha256 recorded)
- `GET /interventions/{id}/ndvi` – Sentinel-2 NDVI before vs after the practice

## Production notes
- **Methodology:** factors live in `app/data/methodology.json` and are **illustrative placeholders**. Copy it, fill in your registry's
  (e.g. Verra VM0042) values, and set `METHODOLOGY_FILE`. The methodology name/version is stored per log and printed on certificates;
  `buffer_pool_ratio` withholds a non-permanence buffer. Real credits also need registry validation/verification, which code can't provide.
- **Migrations:** Alembic (`alembic upgrade head`; the Docker image runs it on boot). Set `AUTO_CREATE_SCHEMA=false` in production.
  An existing database created by the old `create_all`: run `alembic stamp 0001` once, then `alembic upgrade head`.
- **Plot checks (shapely, no PostGIS):** malformed/self-intersecting polygons, acreage that disagrees with the drawn area (>50%), and
  overlap with any existing plot (>5% of the smaller footprint) are rejected. Candidates are prefiltered by lat/lon; for very large
  datasets move to PostGIS with a GiST index.
- **Evidence:** `REQUIRE_EVIDENCE_FOR_APPROVAL=true` makes auditors unable to approve logs without attachments. Add antivirus scanning
  if you accept uploads from untrusted users.
- **Storage:** `STORAGE_BACKEND=local|s3` for certificates and evidence (S3, MinIO, R2 via `S3_ENDPOINT_URL`). The S3 path is
  implemented with boto3 but not exercised by the tests.
- **Hardening:** CORS allow-list (`CORS_ORIGINS`), per-IP login/password rate limits (in-process; also limit at your proxy),
  admin user management, deactivation (tokens stop working immediately), and `ENVIRONMENT=production` refuses to start with the
  default secret/admin password. Password reset is admin-driven; self-service email reset needs an email provider.
- **Satellite check:** uses the public Earth Search STAC API plus `rasterio` COG reads, picking the least-cloudy scene by scene-level
  cloud cover. It is a signal for auditors, not proof; it was unit-tested with mocks only, so try it on a real plot first.
