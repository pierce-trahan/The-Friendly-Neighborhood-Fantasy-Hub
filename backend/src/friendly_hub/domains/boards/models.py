from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class PersonalBoardRow(Base):
    __tablename__ = "personal_board"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    league_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("league_profile.id", ondelete="SET NULL"),
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class BoardTierRow(Base):
    __tablename__ = "board_tier"
    __table_args__ = (
        UniqueConstraint("board_id", "name", name="uq_board_tier_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("personal_board.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    tier_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class BoardEntryRow(Base):
    __tablename__ = "board_entry"
    __table_args__ = (
        UniqueConstraint("board_id", "player_id", name="uq_board_entry_player"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("personal_board.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        index=True,
        nullable=False,
    )
    tier_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("board_tier.id", ondelete="SET NULL"),
    )
    manual_order: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
