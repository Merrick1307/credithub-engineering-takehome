"""Run Alembic safely against either a fresh or application-created database."""

from __future__ import annotations

import subprocess

from sqlalchemy import inspect

from app.db import engine
from app.models import Base


def main() -> None:
    tables = set(inspect(engine).get_table_names())
    application_tables = set(Base.metadata.tables)

    # Older deployments used Base.metadata.create_all(), which creates the full
    # current schema but has no Alembic version row. Creating revision 001 over
    # that schema is neither necessary nor safe; record it as current instead.
    if "alembic_version" not in tables and application_tables.issubset(tables):
        print("Existing application schema found without Alembic history; stamping head.")
        subprocess.run(["alembic", "stamp", "head"], check=True)
        return

    subprocess.run(["alembic", "upgrade", "head"], check=True)


if __name__ == "__main__":
    main()
