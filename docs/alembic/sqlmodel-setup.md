---
source: https://alembic.sqlalchemy.org/en/latest/tutorial.html
fetched: 2025-01-14
summary: Alembic migrations with SQLModel and async PostgreSQL
---

# Alembic with SQLModel (Async PostgreSQL)

Alembic handles database schema migrations. Works with SQLModel via SQLAlchemy.

## Installation

```bash
uv add alembic  # or pip install alembic
```

## Initial Setup

For async PostgreSQL projects:

```bash
alembic init -t async alembic
```

This creates:
- `alembic.ini` - Main configuration
- `alembic/env.py` - Migration environment
- `alembic/versions/` - Migration files
- `alembic/script.py.mako` - Template

## Configuration

### alembic.ini

```ini
[alembic]
script_location = %(here)s/alembic
sqlalchemy.url = postgresql+asyncpg://user:pass@localhost/dbname
file_template = %(rev)s_%(slug)s
```

**Note:** Escape `%` in passwords by doubling them (`%%`).

### env.py for SQLModel + Async

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import your SQLModel models
from promptgrimoire.models import SQLModel  # Your base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata from SQLModel
target_metadata = SQLModel.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    """Create async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

## Creating Migrations

### Manual Migration

```bash
alembic revision -m "create user table"
```

Creates a file like `1975ea83b712_create_user_table.py`:

```python
"""create user table

Revision ID: 1975ea83b712
Revises:
Create Date: 2025-01-14
"""
from alembic import op
import sqlalchemy as sa

revision = '1975ea83b712'
down_revision = None
branch_labels = None

def upgrade():
    op.create_table(
        'user',
        sa.Column('id', sa.UUID, primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_user_email', 'user', ['email'])

def downgrade():
    op.drop_index('ix_user_email')
    op.drop_table('user')
```

### Auto-generate from Models

```bash
alembic revision --autogenerate -m "add conversation table"
```

Alembic compares models to database and generates migration. Requires `target_metadata` to be set in `env.py`.

## Running Migrations

```bash
# Apply all migrations
alembic upgrade head

# Apply specific revision
alembic upgrade ae1027a6acf

# Relative upgrade
alembic upgrade +2
```

## Rolling Back

```bash
# One step back
alembic downgrade -1

# Return to base (no migrations)
alembic downgrade base

# Specific revision
alembic downgrade 1975ea83b712
```

## Viewing Status

```bash
# Current revision
alembic current

# Full history
alembic history --verbose

# Recent history
alembic history -r-3:current
```

## SQLModel Integration Pattern

In your models file:

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import UUID, uuid4

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Alembic will detect changes to these models when using `--autogenerate`.
