from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class AppConfigurationRow(Base):
    __tablename__ = "app_configuration"
    __table_args__ = (CheckConstraint("id = 1", name="ck_app_configuration_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
