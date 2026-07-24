from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class LeagueProfileRow(Base):
    __tablename__ = "league_profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[str] = mapped_column(String(32), nullable=False)
