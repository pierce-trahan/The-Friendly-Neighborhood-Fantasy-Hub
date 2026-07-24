from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class PlayerRow(Base):
    __tablename__ = "player"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    suffix: Mapped[str | None] = mapped_column(String(16))
    search_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    team: Mapped[str | None] = mapped_column(String(8))
    primary_position: Mapped[str] = mapped_column(String(16), nullable=False)
    fantasy_positions_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rookie_class: Mapped[int | None] = mapped_column(Integer)
    is_rookie: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class PlayerExternalIdRow(Base):
    __tablename__ = "player_external_id"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_player_external_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String(32), nullable=False)


class PlayerRelevanceRow(Base):
    __tablename__ = "player_relevance"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "reason",
            "reference_id",
            name="uq_player_relevance_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(36))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class PlayerImportSessionRow(Base):
    __tablename__ = "player_import_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ambiguous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ignored_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    committed_at: Mapped[str | None] = mapped_column(String(32))


class PlayerImportRow(Base):
    __tablename__ = "player_import_row"
    __table_args__ = (
        UniqueConstraint("session_id", "row_number", name="uq_player_import_row_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player_import_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_candidate_json: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_player_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("player.id"),
    )
    resolved_player_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("player.id"),
    )
    candidate_player_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[str] = mapped_column(String(500), nullable=False)


class PlayerMappingDecisionRow(Base):
    __tablename__ = "player_mapping_decision"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_row_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player_import_row.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    player_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("player.id"))
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
