#!/bin/bash
set -e

# Initialize alembic version tracking if the DB was set up before alembic.
# Base.metadata.create_all() creates tables automatically, so alembic needs
# to know which migrations are already reflected in the schema.
python -c "
import asyncio
from sqlalchemy import text
from app.database import engine

KNOWN_BASELINE = '006_add_thumbnail_key'

async def init():
    async with engine.begin() as conn:
        r = await conn.execute(text(
            \"SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name='alembic_version')\"
        ))
        if not r.scalar():
            await conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
            await conn.execute(text(f\"INSERT INTO alembic_version VALUES ('{KNOWN_BASELINE}')\"))
            print(f'Initialized alembic_version at {KNOWN_BASELINE}')
        else:
            r2 = await conn.execute(text('SELECT version_num FROM alembic_version'))
            row = r2.first()
            if not row:
                await conn.execute(text(f\"INSERT INTO alembic_version VALUES ('{KNOWN_BASELINE}')\"))
                print(f'Stamped empty alembic_version to {KNOWN_BASELINE}')
            elif row[0].startswith('00') and row[0] < KNOWN_BASELINE:
                await conn.execute(text(f\"UPDATE alembic_version SET version_num = '{KNOWN_BASELINE}'\"))
                print(f'Updated alembic_version from {row[0]} to {KNOWN_BASELINE}')
            else:
                print(f'Alembic version: {row[0]}')
    await engine.dispose()

asyncio.run(init())
"

# Apply pending migrations
alembic upgrade head

# Idempotent column additions (runs before uvicorn to avoid race conditions)
python -c "
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
"

# Start the server (multi-process: UVICORN_WORKERS env var, default 2)
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-2}
