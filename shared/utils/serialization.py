from typing import Any, Dict
from datetime import time
from shared.utils.time_formatter import format_time


def model_dump_with_time_format(
    model: Any,
    time_format: str = "24h",
    mode: str = "json"
) -> Dict[str, Any]:
    """
    Serializa un modelo Pydantic/SQLModel aplicando formato de hora.

    Args:
        model: Modelo a serializar
        time_format: "24h" o "12h"
        mode: Modo de serialización (default: "json")

    Returns:
        Dict con campos de tiempo formateados
    """
    # Serializar el modelo normalmente
    data = model.model_dump(mode=mode)

    # Iterar sobre campos y formatear los de tipo time
    for key, value in data.items():
        # Obtener el campo original del modelo para verificar el tipo
        model_field = getattr(model, key, None)

        # Si es un campo time, aplicar formato
        if isinstance(model_field, time):
            data[key] = format_time(model_field, time_format)

    return data


def serialize_trips_with_format(trips: list, time_format: str = "24h") -> list:
    """
    Helper específico para serializar lista de trips con formato de hora.
    """
    return [
        model_dump_with_time_format(trip, time_format)
        for trip in trips
    ]
