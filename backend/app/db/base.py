from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 모델의 공통 베이스."""

    metadata = MetaData(schema="public")
    type_annotation_map = {
        str: Text(),
        datetime: DateTime(timezone=True),
        UUID: PostgreSQLUUID(as_uuid=True),
    }
