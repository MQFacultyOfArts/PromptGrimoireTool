---
source: https://sqlmodel.tiangolo.com/
fetched: 2025-01-13
summary: SQLModel - Pydantic + SQLAlchemy ORM for Python
---

# SQLModel Overview

SQLModel combines Pydantic and SQLAlchemy for database interactions. Created by the FastAPI author.

## Key Features

- Type annotation-based design
- Excellent editor autocompletion
- Minimal code duplication
- Functions as both SQLAlchemy and Pydantic model

## Basic Pattern

Models inherit from `SQLModel` with `table=True`:

```python
from sqlmodel import SQLModel, Field

class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    secret_name: str
    age: int | None = None
```

## Database Operations

```python
from sqlmodel import create_engine, Session, select

engine = create_engine("postgresql://user:pass@localhost/db")
SQLModel.metadata.create_all(engine)

# Insert
with Session(engine) as session:
    hero = Hero(name="Spider-Man", secret_name="Peter Parker")
    session.add(hero)
    session.commit()

# Query
with Session(engine) as session:
    statement = select(Hero).where(Hero.name == "Spider-Man")
    hero = session.exec(statement).first()
```

## Relationships

```python
from sqlmodel import Relationship

class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    heroes: list["Hero"] = Relationship(back_populates="team")

class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    team_id: int | None = Field(default=None, foreign_key="team.id")
    team: Team | None = Relationship(back_populates="heroes")
```

## Async Support

SQLModel supports async operations with SQLAlchemy's async engine:

```python
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")

async with AsyncSession(engine) as session:
    statement = select(Hero)
    result = await session.exec(statement)
    heroes = result.all()
```

## PostgreSQL Driver

For async PostgreSQL, use `asyncpg`:

```bash
pip install asyncpg
```

Connection string: `postgresql+asyncpg://user:pass@host/db`

## Migrations

SQLModel doesn't include migrations. Use Alembic:

```bash
pip install alembic
alembic init migrations
```

## PromptGrimoire Schema Mapping

```python
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from uuid import UUID, uuid4

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Class(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    owner_id: UUID = Field(foreign_key="user.id")
    invite_code: str = Field(unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Conversation(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    class_id: UUID = Field(foreign_key="class.id")
    owner_id: UUID = Field(foreign_key="user.id")
    raw_text: str
    crdt_state: bytes  # pycrdt serialized state
    created_at: datetime = Field(default_factory=datetime.utcnow)
```
