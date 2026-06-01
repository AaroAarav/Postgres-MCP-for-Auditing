import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import psycopg
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global variable to hold our connection pool
_pool: AsyncConnectionPool | None = None

async def init_pool() -> None:
    """Initializes the async connection pool."""
    global _pool
    if _pool is None:
        # We pass application_name and statement_timeout cleanly via kwargs
        # instead of hacking them into the connection string URI.
        pool_kwargs = {
            "autocommit": False,
            "application_name": "pg-auditor-mcp",
            "options": f"-c statement_timeout={settings.statement_timeout_ms}"
        }
        
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            timeout=settings.pool_timeout,
            kwargs=pool_kwargs
        )
        
        # Explicitly await the opening of the pool to resolve the RuntimeWarning
        await _pool.open()
        logger.info(f"✅ Connection pool initialized (Min: {settings.pool_min_size}, Max: {settings.pool_max_size})")

async def close_pool() -> None:
    """Gracefully closes the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("🛑 Connection pool closed.")

@asynccontextmanager
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((psycopg.OperationalError, psycopg.errors.AdminShutdown)),
    reraise=True
)
async def get_db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    Acquires a connection from the pool.
    Automatically retries on transient network/database errors using exponential backoff.
    """
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool() first.")
    
    async with _pool.connection() as conn:
        try:
            yield conn
        except psycopg.Error as e:
            logger.error(f"Database error during operation: {e}")
            raise