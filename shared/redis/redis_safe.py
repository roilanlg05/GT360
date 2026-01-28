import logging
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


async def safe_redis_call(
    op: Callable[..., Awaitable[Any]],
    *args,
    context: str = "",
    default: Any = None,
    logger_override: Optional[logging.Logger] = None,
    **kwargs,
) -> Any:
    """
    Execute a Redis operation in best-effort mode.

    - Returns the Redis result on success.
    - Returns `default` on any redis connection/timeout/other error.
    - Logs the failure but does not raise, to keep callers from breaking
      when Redis is temporarily unavailable.
    """
    log = logger_override or logger
    try:
        return await op(*args, **kwargs)
    except (redis.ConnectionError, redis.TimeoutError) as exc:
        log.warning("Redis %s failed: %s", context or op.__name__, exc)
        return default
    except Exception as exc:
        log.error("Redis %s unexpected error: %s", context or op.__name__, exc)
        return default
