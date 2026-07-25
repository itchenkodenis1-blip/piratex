#!/bin/bash
set -e

# Debug: check Railway env vars
echo "DEBUG: JWT_SECRET=$(if [ -n \"$JWT_SECRET\" ]; then echo 'SET'; else echo 'EMPTY'; fi)"
echo "DEBUG: DATABASE_URL=$(if [ -n \"$DATABASE_URL\" ]; then echo 'SET'; else echo 'EMPTY'; fi)"
echo "DEBUG: REDIS_URL=$(if [ -n \"$REDIS_URL\" ]; then echo 'SET'; else echo 'EMPTY'; fi)"
echo "DEBUG: PORT=$PORT"

# Fallback: generate JWT_SECRET if Railway didn't pass it
if [ -z "$JWT_SECRET" ]; then
  JWT_SECRET=$(openssl rand -hex 32)
  export JWT_SECRET
  echo "WARNING: JWT_SECRET not set by Railway — generated temporary key"
fi

# Initialize alembic version tracking if the DB was set up before alembic.
# Base.metadata.create_all() creates tables automatically, so alembic needs
# to know which migrations are already reflected in the schema.
python3 << 'PYEOF'
import asyncio
from sqlalchemy import text
from app.database import engine
from app.database import Base
import app.models  # noqa: F401 — register all ORM models with Base.metadata

KNOWN_BASELINE = '015'

async def init():
    async with engine.begin() as conn:
        # Create all ORM tables first (required before alembic migrations)
        await conn.run_sync(Base.metadata.create_all)
        print('Base.metadata.create_all() done')

        r = await conn.execute(text(
            "SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name='alembic_version')"
        ))
        if not r.scalar():
            await conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{KNOWN_BASELINE}')"))
            print(f'Initialized alembic_version at {KNOWN_BASELINE}')
        else:
            r2 = await conn.execute(text('SELECT version_num FROM alembic_version'))
            row = r2.first()
            if row and row[0] == KNOWN_BASELINE:
                print(f'Alembic version: {row[0]}')
            else:
                old = row[0] if row else '(none)'
                if not row:
                    await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{KNOWN_BASELINE}')"))
                else:
                    await conn.execute(text(f"UPDATE alembic_version SET version_num = '{KNOWN_BASELINE}'"))
                print(f'Stamped alembic_version from {old} to {KNOWN_BASELINE}')
    await engine.dispose()

asyncio.run(init())
PYEOF

# Apply pending migrations
alembic upgrade head

# Idempotent column additions (runs before uvicorn to avoid race conditions)
python3 << 'PYEOF'
import asyncio
from sqlalchemy import text
from app.database import engine

async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS support_blocked BOOLEAN DEFAULT false'))
        await conn.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 1'))
        await conn.execute(text('ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_url TEXT'))
        print('Column check: support_blocked, token_version, payment_url OK')
    await engine.dispose()

asyncio.run(migrate())
PYEOF

# Start the server (multi-process: UVICORN_WORKERS env var, default 2)
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-2}
