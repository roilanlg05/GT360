from psqlmodel import Column, PSQLModel, table
from psqlmodel.utils import now
from psqlmodel.orm.types import timestamptz, uuid

class TimeFormat:
    H24 = "24h"
    H12 = "12h"


@table(name="user_settings", schema="settings")
class UserSettings(PSQLModel):
    """
    User preference settings table.

    Stores user-specific preferences like time format display.
    Located in settings schema for consistency with other user-related tables.
    """

    user_id: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="CASCADE",
        primary_key=True
    )

    time_format: str = Column(
        max_len=10,
        default=TimeFormat.H24,
        nullable=False,
        index=True
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )

    updated_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )
