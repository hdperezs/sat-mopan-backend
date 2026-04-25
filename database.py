import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Lee la variable de entorno DATABASE_URL que configuras en Railway
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Neon entrega una URL con "postgresql://", SQLAlchemy async necesita "postgresql+asyncpg://"
ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("?sslmode=require&channel_binding=require", "")

engine = create_async_engine(
    ASYNC_URL,
    echo=False,
    connect_args={"ssl": True}   # Neon requiere SSL
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
