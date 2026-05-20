"""
Async SQLAlchemy engine, session factory ve veritabanı yardımcıları.

Kullanım:
    from database import get_db, init_db

    # FastAPI dependency
    async def endpoint(db: AsyncSession = Depends(get_db)):
        ...

    # Uygulama başlangıcında
    await init_db()
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(AsyncAttrs, DeclarativeBase):
    """Tüm ORM modelleri bu sınıftan türer."""

    pass


# ---------------------------------------------------------------------------
# Veritabanı başlatma
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """
    Tüm tabloları oluşturur (yoksa).

    Uygulama başlangıcında bir kez çağrılır (main.py lifespan handler).
    Mevcut tablolar ve veriler korunur; yalnızca eksik tablolar eklenir.
    """
    async with engine.begin() as conn:
        # Import burada yapılır; modüller Base'i extend ettikten sonra
        # metadata'ya kayıt olurlar.
        import models  # noqa: F401  — side-effect: tablo tanımlarını Base'e kaydeder

        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """
    Her HTTP isteği için bağımsız bir AsyncSession açar ve kapatır.

    Örnek:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Scan))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Yardımcı: bağlantı sağlığı kontrolü
# ---------------------------------------------------------------------------


async def check_db_connection() -> bool:
    """
    Veritabanı bağlantısını test eder.

    Returns:
        True → bağlantı başarılı, False → hata var.
    """
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
