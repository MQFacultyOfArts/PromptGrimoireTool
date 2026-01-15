---
source: https://magicstack.github.io/asyncpg/current/usage.html
fetched: 2025-01-14
summary: asyncpg usage - connections, queries, pools, type conversion
---

# asyncpg Usage Guide

asyncpg is a fast async PostgreSQL client library for Python.

## Installation

```bash
pip install asyncpg
# or with uv
uv add asyncpg
```

## Basic Connection

```python
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://postgres@localhost/test')
    await conn.close()

asyncio.run(main())
```

## Query Methods

- **`execute()`** — Runs a statement and returns command status
- **`fetchrow()`** — Retrieves a single row as a Record object
- **`fetchval()`** — Returns a scalar value from the first row
- **`fetch()`** — Returns all matching rows as a list

### Query Parameters

Uses PostgreSQL's native `$1`, `$2` syntax:

```python
row = await conn.fetchrow('SELECT * FROM users WHERE name = $1', 'Bob')
result = await conn.fetchval("SELECT 2 ^ $1", 10)
```

## Transactions

```python
async with connection.transaction():
    await connection.execute("INSERT INTO mytable VALUES(1, 2, 3)")
```

Outside explicit transaction blocks, changes are applied immediately (auto-commit).

## Connection Pools

For applications handling frequent requests:

```python
pool = await asyncpg.create_pool(database='postgres', user='postgres')

async with pool.acquire() as connection:
    result = await connection.fetchval('select 2 ^ $1', power)

await pool.close()
```

## Type Conversion

Automatic conversions:

| PostgreSQL | Python |
|------------|--------|
| Arrays | `list` |
| JSON/JSONB | `str` (default) |
| Dates/Times | `datetime` |
| Numeric | `Decimal` |
| UUID | `uuid.UUID` |
| IP addresses | `ipaddress` objects |

### Custom JSON Codec

```python
import json

await conn.set_type_codec(
    'json',
    encoder=json.dumps,
    decoder=json.loads,
    schema='pg_catalog'
)

data = {'foo': 'bar'}
result = await conn.fetchval('SELECT $1::json', data)
```

## SQLAlchemy/SQLModel Async Integration

For use with SQLModel's async support:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Connection string uses asyncpg driver
engine = create_async_engine("postgresql+asyncpg://user:pass@host/dbname")

async_session = async_sessionmaker(engine, expire_on_commit=False)

async with async_session() as session:
    async with session.begin():
        session.add(MyObject(data="value"))

    result = await session.execute(select(MyObject))
    objects = result.scalars().all()
```

### Critical Notes

- **Concurrency:** A single `AsyncSession` is NOT safe for concurrent tasks
- **Lazy Loading:** Use eager loading (`selectinload()`) to avoid implicit I/O
- **Cleanup:** Always call `await engine.dispose()` when finished

## Complete Example

```python
import asyncio
import asyncpg
from aiohttp import web

async def handle(request):
    pool = request.app['pool']
    power = int(request.match_info.get('power', 10))

    async with pool.acquire() as connection:
        async with connection.transaction():
            result = await connection.fetchval('select 2 ^ $1', power)
            return web.Response(text=f"2 ^ {power} is {result}")

async def init_db(app):
    app['pool'] = await asyncpg.create_pool(
        database='postgres',
        user='postgres'
    )
    yield
    await app['pool'].close()

def init_app():
    app = web.Application()
    app.cleanup_ctx.append(init_db)
    app.router.add_route('GET', '/{power:\\d+}', handle)
    return app

web.run_app(init_app())
```
