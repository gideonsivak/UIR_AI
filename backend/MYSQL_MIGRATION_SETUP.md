# GIDEON PLANT: MySQL Migration Setup

## What changed

The backend has been migrated from JSON-backed User and Plant CRUD to SQLAlchemy models backed by MySQL.

- `app/database.py` loads `DATABASE_URL` from `backend/.env` and provides SQLAlchemy sessions.
- `app/models.py` defines `users`, `plants`, and `plant_analyses` tables.
- User and Plant routes now use MySQL while preserving the existing string IDs and API response shapes.
- Plant analyses are stored in a one-to-one `plant_analyses` table, preserving the existing Save Analysis behavior.
- Gemini analysis and AI error handling were not changed.
- Existing `data/users.json` and `data/plants.json` are preserved as read-only migration sources.

## Migration files

- `alembic.ini`
- `migrations/env.py`
- `migrations/versions/20261009_01_create_gideon_plant_tables.py`
- `scripts/migrate_json_to_mysql.py`

## Database URL

Set a working MySQL connection string in `backend/.env`. Do not commit this file or expose its password.

```env
DATABASE_URL=mysql+pymysql://USERNAME:URL_ENCODED_PASSWORD@127.0.0.1:3306/gideon_plant_db
```

## Finish the migration

From the `backend` directory:

```bash
source .venv/bin/activate
alembic -c alembic.ini upgrade head
python scripts/migrate_json_to_mysql.py
```

The importer is idempotent: it imports only records whose IDs are not already in MySQL. It never edits, overwrites, or deletes JSON files.

## Current status

The application code and isolated database tests are complete. Applying the migration to MySQL was blocked because the configured MySQL account was rejected with error 1045 (access denied). Update `DATABASE_URL` with valid MySQL credentials, then run the commands above.

## Verification

- 12 automated backend tests passed.
- Tests cover User, Plant, and Plant Analysis CRUD relationships using an isolated SQLite database.
- Alembic generated valid MySQL DDL for all three tables.
