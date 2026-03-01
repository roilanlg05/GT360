# Trips WebSocket

## Endpoint
```
ws://host/ws/trips?location_id={uuid}&token={jwt}
```

## Connection Flow

```
Client                          Backend                         Redis
  |                                |                               |
  |--- WS Connect (token) -------->|                               |
  |                                |-- Validate JWT                |
  |                                |-- Check location access       |
  |                                |                               |
  |<-- {type: "snapshot"} ---------|                               |
  |    (all trips + location_info) |                               |
  |                                |-- Subscribe loc:{id} -------->|
  |                                |                               |
  |<-- {type: "trips_batch"} ------|<-- Redis pub/sub -------------|
  |                                |                               |
```

## Server → Client

| Type | When | Payload |
|------|------|---------|
| `snapshot` | On connect | `{type, location_id, location_info, trips[]}` |
| `trips_batch` | WAL trigger (insert/update/delete) | `{type, location_id, events[]}` |
| `batch_delete_started` | Bulk delete started (suppress WAL noise) | `{type, location_id, airline}` |
| `trips_deleted` | Bulk delete completed | `{type, location_id, trips_deleted_count, airline?, pick_up_date?, status?}` |
| `location_delete_started` | Location being deleted | `{type, location_id, trips_count}` |
| `location_deleted` | Location fully deleted | `{type, location_id, trips_deleted}` |
| `step_applied` | Ground filter applied | `{type, location_id, filter_type, ...}` |
| `step_reverted` | Ground filter reverted | `{type, location_id, filter_type, ...}` |
| `subscribed` | Response to `subscribe` action | `{type, location_id}` |
| `unsubscribed` | Response to `unsubscribe` action | `{type, location_id}` |
| `pong` | Response to `ping` | `{type: "pong"}` |
| `error` | Auth or unknown action | `{type, code?, detail}` |

### `snapshot` — `location_info` fields

```json
{
  "id": "uuid",
  "name": "SDF",
  "timezone": "America/Kentucky/Louisville"
}
```

### `trips_batch` — event structure

```json
{
  "type": "trips_batch",
  "location_id": "uuid",
  "events": [
    { "event_type": "insert", "trip_id": "uuid", "trip": { } },
    { "event_type": "update", "trip_id": "uuid", "trip": { } },
    { "event_type": "delete", "trip_id": "uuid" }
  ]
}
```

## Client → Server

| Action | Description | Payload |
|--------|-------------|---------|
| `ping` | Keep-alive, revalidates token | `{action: "ping", token: "<jwt>"}` |
| `subscribe` | Re-confirm subscription | `{action: "subscribe"}` |
| `unsubscribe` | Signal intent to unsubscribe | `{action: "unsubscribe"}` |

## Close Codes

| Code | Reason |
|------|--------|
| `1008` | Auth failure — invalid/expired token or no location access |
| `1011` | Unexpected server error |

## Redis

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `loc:{location_id}` | pub/sub channel | — | All events for this location |
| `loc:{location_id}:trips` | set | 300s | Trip ID index for snapshot |
| `trip:{trip_id}` | string (JSON) | 300s | Cached trip data for snapshot |
