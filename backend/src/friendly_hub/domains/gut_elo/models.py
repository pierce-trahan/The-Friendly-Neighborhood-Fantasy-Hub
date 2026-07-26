from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class GutEloSessionRow(Base):
    __tablename__ = "gut_elo_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("personal_board.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    queue_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[str | None] = mapped_column(String(16))
    tier_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(32))


class GutEloParticipantRow(Base):
    __tablename__ = "gut_elo_participant"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "player_id",
            name="uq_gut_elo_participant_player",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("gut_elo_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        index=True,
        nullable=False,
    )
    starting_manual_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_tier_name: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class GutEloActionRow(Base):
    __tablename__ = "gut_elo_action"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "sequence_number",
            name="uq_gut_elo_action_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("gut_elo_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_a_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    player_b_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    undone_at: Mapped[str | None] = mapped_column(String(32))
