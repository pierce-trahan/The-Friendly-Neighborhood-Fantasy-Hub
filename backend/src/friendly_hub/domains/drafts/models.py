from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class DraftSessionRow(Base):
    __tablename__ = "draft_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    board_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_board.id"), index=True, nullable=False
    )
    league_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("league_profile.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    draft_format: Mapped[str] = mapped_column(String(16), nullable=False)
    third_round_reversal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    round_count: Mapped[int] = mapped_column(Integer, nullable=False)
    user_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    pick_timer_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reset_from_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("draft_session.id", ondelete="SET NULL")
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(32))


class DraftTeamRow(Base):
    __tablename__ = "draft_team"
    __table_args__ = (
        UniqueConstraint("session_id", "draft_slot", name="uq_draft_team_slot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    draft_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_user: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DraftCandidateRow(Base):
    __tablename__ = "draft_candidate"
    __table_args__ = (
        UniqueConstraint("session_id", "player_id", name="uq_draft_candidate_player"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("player.id"), index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    search_name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_position: Mapped[str] = mapped_column(String(16), nullable=False)
    fantasy_positions_json: Mapped[str] = mapped_column(Text, nullable=False)
    team: Mapped[str | None] = mapped_column(String(8))
    player_status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_rookie: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rookie_class: Mapped[int | None] = mapped_column(Integer)
    snapshot_source: Mapped[str] = mapped_column(String(24), nullable=False)
    manual_rank: Mapped[int | None] = mapped_column(Integer)
    tier_name: Mapped[str | None] = mapped_column(String(80))
    tier_color: Mapped[str | None] = mapped_column(String(32))
    tier_order: Mapped[int | None] = mapped_column(Integer)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False)
    board_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class DraftPickRow(Base):
    __tablename__ = "draft_pick"
    __table_args__ = (
        UniqueConstraint("session_id", "overall_pick", name="uq_draft_pick_overall"),
        UniqueConstraint("session_id", "player_id", name="uq_draft_pick_player"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pick_in_round: Mapped[int] = mapped_column(Integer, nullable=False)
    selecting_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("player.id"))
    recorded_at: Mapped[str | None] = mapped_column(String(32))
    client_entered_at: Mapped[str | None] = mapped_column(String(64))
    correction_count: Mapped[int] = mapped_column(Integer, nullable=False)


class DraftPickRevisionRow(Base):
    __tablename__ = "draft_pick_revision"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "session_revision", name="uq_draft_pick_revision"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    pick_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("draft_pick.id", ondelete="CASCADE"), nullable=False
    )
    session_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_player_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("player.id")
    )
    next_player_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("player.id")
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
