#!/usr/bin/env python3
"""
Create database (if needed) and run migrations.
Run: python scripts/init_db.py
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    # Try alembic first - database might already exist
    print("Running migrations...")
    result = subprocess.run(["alembic", "upgrade", "head"], cwd=Path(__file__).parent.parent)
    if result.returncode == 0:
        print("Database ready.")
        return 0

    # If failed, try creating DB first (requires psql)
    print("Migration failed. Trying to create database...")
    from app.core.config import get_settings
    settings = get_settings()
    url = settings.database_url_sync
    # Parse: postgresql://user:pass@host:port/dbname
    if "postgresql" not in url:
        print("Not a PostgreSQL URL. Run: alembic upgrade head")
        return 1

    # Extract: postgresql://user:pass@host:port/dbname
    from urllib.parse import urlparse
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/").split("?")[0] or "support_ai"
    create_url = f"postgresql://{parsed.netloc}/postgres"

    try:
        import psycopg2
        conn = psycopg2.connect(create_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {db_name}")
            print(f"Created database {db_name}")
        conn.close()
    except Exception as e:
        print(f"Could not create database: {e}")
        print("Ensure PostgreSQL is running and create database manually:")
        print(f"  createdb {db_name}")
        return 1

    # Retry migrations
    result = subprocess.run(["alembic", "upgrade", "head"], cwd=Path(__file__).parent.parent)
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
