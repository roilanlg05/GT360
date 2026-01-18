from datetime import time
from typing import Optional


def format_time(t: Optional[time], format_type: str = "24h") -> Optional[str]:
    """
    Formatea un objeto time según el formato especificado.

    Args:
        t: Objeto time de Python
        format_type: "24h" (militar) o "12h" (AM/PM)

    Returns:
        String formateado o None si t es None

    Examples:
        format_time(time(16, 30), "24h") -> "16:30"
        format_time(time(16, 30), "12h") -> "04:30 PM"
        format_time(time(0, 0), "12h") -> "12:00 AM"
        format_time(time(12, 0), "12h") -> "12:00 PM"
    """
    if t is None:
        return None

    if format_type == "24h":
        # Formato militar: HH:MM (sin segundos)
        return t.strftime("%H:%M")

    elif format_type == "12h":
        # Formato AM/PM: hh:MM AM/PM (sin segundos)
        return t.strftime("%I:%M %p")

    else:
        # Default: formato militar
        return t.strftime("%H:%M")
