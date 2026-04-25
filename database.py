import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Neon usa postgresql://, SQLAlchemy async necesita postgresql+asyncpg://
ASYNC_URL = DATABASE_URL \
    .replace("postgresql://", "postgresql+asyncpg://") \
    .split("?")[0]  # Quitar parametros SSL que asyncpg no entiende

engine = create_async_engine(
    ASYNC_URL,
    echo=False,
    pool_pre_ping=True,    # Verifica conexion antes de usarla
    pool_recycle=300,      # Recicla conexiones cada 5 minutos
    pool_size=5,
    max_overflow=10,
    connect_args={"ssl": True}
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
