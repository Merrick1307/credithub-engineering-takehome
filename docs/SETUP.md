# Setup guide

## Docker (recommended)

Copy any required overrides into your shell or a `.env` file, then run:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

The frontend is available on `http://localhost:5137`; the API is on port `8137`.
The seeded admin credential is `ADMIN_TOKEN` (default: `dev-admin-secret`).

The first startup runs Alembic migrations and idempotent demo seeding. Set
`RUN_MIGRATIONS=0` only when the target schema is already managed elsewhere.

## Reset development data

This removes the local Postgres volume:

```bash
docker compose -f deploy/docker-compose.yml down -v
docker compose -f deploy/docker-compose.yml up --build
```

## Local development

One command run:
```bash
./run-local.sh
```

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --port 8137
```

In another terminal, run `npm install && npm run dev` from `frontend/`.

## Verification

```bash
pytest -q
npm --prefix frontend run build
```
