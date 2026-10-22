import logging
from typing import Optional
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """
    Manages the application-level asynchronous Redis connection pool.
    Provides non-blocking client access, health probes, and graceful shutdown.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url: str = redis_url or settings.REDIS_URL
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None
        self._is_connected: bool = False

    async def initialize(self) -> None:
        """Initializes the async Redis connection pool and verifies connectivity."""
        if self._pool is not None:
            return

        try:
            logger.info(f"Initializing Redis connection pool for {self.redis_url}...")
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=50,
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=5.0,
                retry_on_timeout=True
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            # Lightweight connectivity probe
            await self._client.ping()
            self._is_connected = True
            logger.info("Redis connection established successfully.")
        except Exception as exc:
            self._is_connected = False
            self._client = None
            self._pool = None
            logger.warning(
                f"Redis connection initialization could not reach Redis server ({exc}). "
                "The application will operate in degraded mode without distributed real-time events."
            )

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Returns the active async Redis client instance, or None if uninitialized/unreachable."""
        if not self._is_connected:
            if self._pool is None:
                await self.initialize()
            if not self._is_connected:
                return None
        return self._client

    async def ping(self) -> bool:
        """Health check probe returning True if Redis responds to PING within timeout."""
        if not self._client:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        """Gracefully closes all Redis connections and the pool."""
        logger.info("Closing Redis connection pool...")
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")
            finally:
                self._client = None

        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting Redis pool: {e}")
            finally:
                self._pool = None

        self._is_connected = False
        logger.info("Redis connection pool closed.")


# Singleton Redis manager instance
redis_manager = RedisManager()


async def get_redis_client() -> Optional[aioredis.Redis]:
    """Dependency helper returning active Redis client."""
    return await redis_manager.get_client()
