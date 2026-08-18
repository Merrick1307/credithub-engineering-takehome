"""Run Alembic safely against either a fresh or application-created database."""

from __future__ import annotations

import subprocess
import os

from sqlalchemy import inspect, text

from app.adapters.persistence.db import engine
from app.adapters.persistence.sqlalchemy_backend.models import Base


def main() -> None:
    tables = set(inspect(engine).get_table_names())
    application_tables = set(Base.metadata.tables)

    # Older deployments used Base.metadata.create_all(), which creates the full
    # current schema but has no Alembic version row. Creating revision 001 over
    # that schema is neither necessary nor safe; record it as current instead.
    if "alembic_version" not in tables and application_tables.issubset(tables):
        print("Existing application schema found without Alembic history; stamping head.")
        subprocess.run(["alembic", "stamp", "head"], check=True)
    else:
        subprocess.run(["alembic", "upgrade", "head"], check=True)

    # Compose changes this value with every migration. This catches the subtle
    # case where Docker reuses a completed, stale migrations container while
    # freshly created workers contain a newer ORM model.
    expected_revision = os.getenv("EXPECTED_ALEMBIC_REVISION")
    if expected_revision:
        with engine.connect() as connection:
            actual_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if actual_revision != expected_revision:
            raise RuntimeError(
                f"Database is at Alembic revision {actual_revision}; expected {expected_revision}. "
                "Rebuild and rerun the migrations service."
            )
        print(f"Database schema verified at Alembic revision {actual_revision}.")


if __name__ == "__main__":
    main()
