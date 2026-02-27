from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from psqlmodel import Select, AsyncSession
from uuid import UUID
from typing import Optional

from shared.db.db_config import engine
from shared.db.schemas import Driver, User
from features.auth.utils import decode_token
from features.drivers.utils.location_ws_manager import driver_location_manager

router = APIRouter()


async def _get_driver_info(driver_id: str, org_id: str) -> Optional[dict]:
    """Fetch driver name and location_id from DB."""
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        return None

    async with AsyncSession(engine) as session:
        row = await session.exec(
            Select(Driver.location_id, User.first_name, User.last_name)
            .From(Driver)
            .Join(User).On(Driver.id == User.id)
            .Where(Driver.id == driver_uuid)
        ).first()

    if not row:
        return None

    return {
        "driver_id": driver_id,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "location_id": str(row.location_id) if row.location_id else None,
    }


@router.websocket("/ws/driver-locations")
async def ws_driver_locations(
    ws: WebSocket,
    token: str,
    location_id: Optional[str] = None,
):
    """
    WebSocket endpoint for driver location sharing.

    Role determines behavior (from JWT):
      - driver: sends location updates + receives other drivers' locations (if sharing enabled)
      - manager: receives location updates (filtered by location_id if provided)

    Query params:
      - token: JWT access token
      - location_id: (manager only) filter to drivers at this location
    """
    # Authenticate
    try:
        claims = decode_token(token)
    except Exception:
        await ws.close(code=1008)
        return

    metadata = claims.get("metadata")
    if not metadata:
        await ws.close(code=1008)
        return

    role = metadata.get("role")
    org_id = metadata.get("organization_id")

    if not org_id or role not in ("driver", "manager"):
        await ws.close(code=1008)
        return

    # ─── DRIVER flow ──────────────────────────────────────────────────────────
    if role == "driver":
        driver_id = claims.get("sub")
        if not driver_id:
            await ws.close(code=1008)
            return

        # Fetch name/location_id from DB once at connect time
        driver_info = await _get_driver_info(driver_id, org_id)
        if not driver_info:
            await ws.close(code=1008)
            return

        driver_location_id = driver_info.get("location_id")

        await ws.accept()

        # Register driver in location room (even if sharing is off, for toggle-on scenario)
        if driver_location_id:
            await driver_location_manager.connect_driver(
                ws, org_id, driver_id, driver_location_id, driver_info
            )

        # Ensure org listener is running (for control channel + location broadcasts)
        await driver_location_manager.ensure_org_listener(org_id)

        # If sharing is enabled, send initial snapshot of other drivers at same location
        if driver_location_id and await driver_location_manager.is_sharing_enabled(org_id):
            snapshot = await driver_location_manager.get_all_driver_locations(
                org_id, driver_location_id
            )
            # Exclude self from snapshot
            snapshot = [d for d in snapshot if d.get("driver_id") != driver_id]
            await ws.send_json({"type": "driver_snapshot", "drivers": snapshot})

        try:
            while True:
                msg = await ws.receive_json()
                action = msg.get("action")

                if action == "location_update":
                    lat = msg.get("lat")
                    lng = msg.get("lng")
                    if lat is None or lng is None:
                        await ws.send_json({"type": "error", "detail": "lat and lng required"})
                        continue

                    location_data = {
                        **driver_info,
                        "lat": lat,
                        "lng": lng,
                    }
                    await driver_location_manager.store_driver_location(
                        org_id, driver_id, location_data
                    )

                elif action == "ping":
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

                else:
                    await ws.send_json({"type": "error", "detail": "Unknown action"})

        except WebSocketDisconnect:
            pass
        except Exception:
            try:
                await ws.close(code=1011)
            except Exception:
                pass
        finally:
            # Clean up driver WS connection from in-memory rooms.
            # Do NOT remove location from Redis — the driver may still be
            # sending updates via HTTP (background mode). The stale cleanup
            # task handles removal of truly inactive drivers.
            await driver_location_manager.disconnect_driver(ws)

    # ─── MANAGER flow ─────────────────────────────────────────────────────────
    else:
        await driver_location_manager.connect(ws, org_id, claims, location_id)
        await driver_location_manager.ensure_org_listener(org_id)

        # Send initial snapshot
        snapshot = await driver_location_manager.get_all_driver_locations(
            org_id, location_id
        )
        await ws.send_json({"type": "snapshot", "drivers": snapshot})

        try:
            while True:
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

                else:
                    await ws.send_json({"type": "error", "detail": "Unknown action"})

        except WebSocketDisconnect:
            await driver_location_manager.disconnect(ws)
        except Exception:
            await driver_location_manager.disconnect(ws)
            try:
                await ws.close(code=1011)
            except Exception:
                pass
