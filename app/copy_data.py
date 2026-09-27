"""Copy every row from one database to another, e.g. the local SQLite file into PostgreSQL.

The target must already have the current schema (`alembic upgrade head`). Rows keep their ids, so
history and ordering survive; Postgres id sequences are moved past the copied ids afterwards.

    uv run python -m app.copy_data sqlite:///data/planner.db postgresql+psycopg://…  [--replace]
"""

import argparse
import sys

from sqlalchemy import Engine, func, insert, select, text
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import Settings
from app.db import make_engine

TABLES = SQLModel.metadata.sorted_tables  # parents before children (foreign keys)


def counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            t.name: conn.execute(select(func.count()).select_from(t)).scalar_one() for t in TABLES
        }


def copy(source: Engine, target: Engine, *, replace: bool) -> dict[str, int]:
    existing = {name: n for name, n in counts(target).items() if n}
    if existing and not replace:
        raise SystemExit(f"Target is not empty ({existing}); pass --replace to overwrite it.")
    with source.connect() as src, target.begin() as dst:  # one transaction: all or nothing
        for table in reversed(TABLES):
            dst.execute(table.delete())
        for table in TABLES:
            rows = [dict(r._mapping) for r in src.execute(select(table))]
            if rows:
                dst.execute(insert(table), rows)
        if target.dialect.name == "postgresql":
            for table in TABLES:
                if "id" in table.c:
                    dst.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'),"
                            f' COALESCE((SELECT MAX(id) FROM "{table.name}"), 1),'
                            f' (SELECT MAX(id) FROM "{table.name}") IS NOT NULL)'
                        )
                    )
    return counts(target)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="SQLAlchemy URL to copy from")
    parser.add_argument("target", help="SQLAlchemy URL to copy into (schema already migrated)")
    parser.add_argument("--replace", action="store_true", help="delete existing rows in target")
    args = parser.parse_args(argv)

    # Same URL handling as the app (relative SQLite paths resolve against the project root).
    source = make_engine(Settings(database_url=args.source).database_url)
    target = make_engine(Settings(database_url=args.target).database_url)
    expected = counts(source)
    copied = copy(source, target, replace=args.replace)
    for name in expected:
        print(f"{name:12} {expected[name]:>6} → {copied[name]:>6}")
    if copied != expected:
        sys.exit("Row counts differ after copying!")
    print("OK")


if __name__ == "__main__":
    main()
