import json
from shared.redis.redis_client import redis_client
from psqlmodel import Select
from features.auth.schemas import Location

async def save_trip_event_to_redis(trip_id: str, event_data: dict):
    """
    Save or update trip event data in Redis by trip_id.
    Args:
        trip_id (str): The location identifier.
        event_data (dict): The event data to store.
    """
    key = f"trip:{trip_id}"
    await redis_client.set(key, json.dumps(event_data))

async def get_trip_event_from_redis(trip_id: str):
    """
    Retrieve trip event data from Redis by location_id.
    Args:
        location_id (str): The location identifier.
    Returns:
        dict or None: The event data if exists, else None.
    """
    key = f"trip:{trip_id}"
    data = await redis_client.get(key)
    return json.loads(data) if data else None

async def get_locations_by_org_id(session, org_id):
    locations = await session.exec(
        Select(Location)
        .Where(Location.organization_id == org_id)
    ).to_dicts()
    return locations