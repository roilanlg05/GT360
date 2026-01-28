"""
Profile WebSocket - Real-time streaming of user profile data.
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from psqlmodel import Select, AsyncSession
from uuid import UUID

from shared.db.db_config import engine
from shared.db.schemas import User
from shared.redis.redis_client import redis_client as redis
from shared.redis.redis_safe import safe_redis_call
from features.auth.utils import decode_token


router = APIRouter()

# Channel prefix for profile updates
PROFILE_CHANNEL_PREFIX = "profile:"


async def _get_user_profile(user_id: str) -> dict | None:
    """Get user profile from database."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return None

    async with AsyncSession(engine) as session:
        user = await session.exec(
            Select(User).Where(User.id == user_uuid)
        ).first()

        if not user:
            return None

        return {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "profile_pic": user.profile_pic,
            "role": user.role,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }


@router.websocket("/ws/profile")
async def ws_profile(ws: WebSocket, token: str):
    """
    WebSocket for real-time profile updates.

    Sends initial profile snapshot on connect, then listens for updates
    via Redis pub/sub.

    Query params:
        token: JWT token for authentication

    Messages from server:
        - snapshot: Initial profile data
        - update: Profile was updated
        - pong: Response to ping

    Messages from client:
        - ping: Keep-alive with token refresh
    """
    # Validate token
    try:
        claims = decode_token(token)
    except Exception:
        await ws.close(code=1008)
        return

    metadata = claims.get("metadata")
    if not metadata:
        await ws.close(code=1008)
        return

    user_id = metadata.get("id")
    if not user_id:
        await ws.close(code=1008)
        return

    await ws.accept()

    # Send initial snapshot
    profile = await _get_user_profile(user_id)
    if profile:
        await ws.send_json({
            "type": "snapshot",
            "data": profile
        })
    else:
        await ws.send_json({
            "type": "error",
            "detail": "Profile not found"
        })
        await ws.close(code=1008)
        return

    # Subscribe to profile updates channel
    channel = f"{PROFILE_CHANNEL_PREFIX}{user_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async def listen_redis():
        """Listen for Redis pub/sub messages."""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    try:
                        payload = json.loads(data)
                        await ws.send_json({
                            "type": "update",
                            "data": payload
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    # Start Redis listener task
    redis_task = asyncio.create_task(listen_redis())

    try:
        while True:
            # Wait for client messages
            msg = await ws.receive_json()
            action = msg.get("action")

            if action == "ping":
                ping_token = msg.get("token")
                if not ping_token:
                    await ws.send_json({"type": "error", "code": 401, "detail": "Token required"})
                    await ws.close(code=1008)
                    return

                try:
                    decode_token(ping_token)
                    await ws.send_json({"type": "pong"})
                except Exception:
                    await ws.send_json({"type": "error", "code": 401, "detail": "Invalid or expired token"})
                    await ws.close(code=1008)
                    return

            elif action == "refresh":
                # Client requests fresh profile data
                profile = await _get_user_profile(user_id)
                if profile:
                    await ws.send_json({
                        "type": "snapshot",
                        "data": profile
                    })

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        # Cleanup
        redis_task.cancel()
        try:
            await redis_task
        except asyncio.CancelledError:
            pass
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def publish_profile_update(user_id: str, profile_data: dict):
    """
    Publish profile update to Redis for WebSocket streaming.

    Call this function when profile is updated via API.
    """
    channel = f"{PROFILE_CHANNEL_PREFIX}{user_id}"
    await safe_redis_call(
        redis.publish,
        channel,
        json.dumps(profile_data),
        context=f"publish {channel}",
    )
