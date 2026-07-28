"""Create the Phase 4 mock persistence tables.

Revision ID: 20260728_0007
Revises: 20260728_0006
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0007"
down_revision: str | None = "20260728_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mock_configuration",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_session_id", sa.String(36), nullable=False),
        sa.Column("seed", sa.String(20), nullable=False),
        sa.Column("rng_version", sa.String(64), nullable=False),
        sa.Column("cpu_engine_version", sa.String(64), nullable=False),
        sa.Column("strategy_definition_version", sa.String(64), nullable=False),
        sa.Column("league_shape_json", sa.Text(), nullable=False),
        sa.Column("league_shape_source_timestamp", sa.String(32)),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("randomness", sa.Integer(), nullable=False),
        sa.Column("current_strategy_key", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("include_in_learning", sa.Boolean(), nullable=False),
        sa.Column("learning_opted_in_at", sa.String(32)),
        sa.Column("learning_withdrawn_at", sa.String(32)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "randomness >= 0 AND randomness <= 100",
            name="ck_mock_configuration_randomness",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_mock_configuration_revision",
        ),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64",
            name="ck_mock_configuration_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["draft_session_id"],
            ["draft_session.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "draft_session_id",
            name="uq_mock_configuration_draft_session",
        ),
    )

    op.create_table(
        "mock_strategy_revision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mock_configuration_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("previous_strategy_key", sa.String(32)),
        sa.Column("next_strategy_key", sa.String(32), nullable=False),
        sa.Column("effective_overall_pick", sa.Integer(), nullable=False),
        sa.Column("user_roster_counts_json", sa.Text(), nullable=False),
        sa.Column("private_user_note", sa.Text()),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "sequence_number >= 1",
            name="ck_mock_strategy_revision_sequence",
        ),
        sa.CheckConstraint(
            "effective_overall_pick >= 1",
            name="ck_mock_strategy_revision_effective_pick",
        ),
        sa.ForeignKeyConstraint(
            ["mock_configuration_id"],
            ["mock_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "mock_configuration_id",
            "sequence_number",
            name="uq_mock_strategy_revision_sequence",
        ),
    )
    op.create_index(
        "ix_mock_strategy_revision_mock_configuration_id",
        "mock_strategy_revision",
        ["mock_configuration_id"],
    )

    op.create_table(
        "mock_cpu_profile",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mock_configuration_id", sa.String(36), nullable=False),
        sa.Column("draft_slot", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("archetype_key", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("draft_sample_count", sa.Integer(), nullable=False),
        sa.Column("pick_sample_count", sa.Integer(), nullable=False),
        sa.Column("tendency_snapshot_json", sa.Text(), nullable=False),
        sa.Column("internal_manager_reference", sa.String(128)),
        sa.Column("source_timestamp", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "draft_slot >= 1",
            name="ck_mock_cpu_profile_slot",
        ),
        sa.CheckConstraint(
            "source IN ('fallback', 'history')",
            name="ck_mock_cpu_profile_source",
        ),
        sa.CheckConstraint(
            "draft_sample_count >= 0",
            name="ck_mock_cpu_profile_draft_samples",
        ),
        sa.CheckConstraint(
            "pick_sample_count >= 0",
            name="ck_mock_cpu_profile_pick_samples",
        ),
        sa.CheckConstraint(
            "confidence IN ('not_applicable', 'low', 'medium', 'high')",
            name="ck_mock_cpu_profile_confidence",
        ),
        sa.CheckConstraint(
            "("
            "source = 'fallback' AND confidence = 'not_applicable' "
            "AND draft_sample_count = 0 AND pick_sample_count = 0"
            ") OR ("
            "source = 'history' AND confidence IN ('low', 'medium', 'high') "
            "AND draft_sample_count >= 3 AND pick_sample_count >= 20"
            ")",
            name="ck_mock_cpu_profile_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["mock_configuration_id"],
            ["mock_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "mock_configuration_id",
            "draft_slot",
            name="uq_mock_cpu_profile_slot",
        ),
    )
    op.create_index(
        "ix_mock_cpu_profile_mock_configuration_id",
        "mock_cpu_profile",
        ["mock_configuration_id"],
    )

    op.create_table(
        "mock_pick_decision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mock_configuration_id", sa.String(36), nullable=False),
        sa.Column("draft_pick_revision_id", sa.String(36), nullable=False),
        sa.Column("overall_pick", sa.Integer(), nullable=False),
        sa.Column("selecting_slot", sa.Integer(), nullable=False),
        sa.Column("chosen_player_id", sa.String(36), nullable=False),
        sa.Column("profile_source", sa.String(16), nullable=False),
        sa.Column("profile_archetype_key", sa.String(32), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("rng_version", sa.String(64), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("component_scores_json", sa.Text(), nullable=False),
        sa.Column("random_audit_json", sa.Text(), nullable=False),
        sa.Column("alternatives_json", sa.Text(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "overall_pick >= 1",
            name="ck_mock_pick_decision_overall_pick",
        ),
        sa.CheckConstraint(
            "selecting_slot >= 1",
            name="ck_mock_pick_decision_selecting_slot",
        ),
        sa.CheckConstraint(
            "profile_source IN ('fallback', 'history')",
            name="ck_mock_pick_decision_profile_source",
        ),
        sa.ForeignKeyConstraint(
            ["mock_configuration_id"],
            ["mock_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["draft_pick_revision_id"],
            ["draft_pick_revision.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["chosen_player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "draft_pick_revision_id",
            name="uq_mock_pick_decision_pick_revision",
        ),
    )
    op.create_index(
        "ix_mock_pick_decision_configuration_overall",
        "mock_pick_decision",
        ["mock_configuration_id", "overall_pick"],
    )

    op.create_table(
        "mock_guidance_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mock_configuration_id", sa.String(36), nullable=False),
        sa.Column("strategy_revision_id", sa.String(36), nullable=False),
        sa.Column("deterministic_event_key", sa.String(128), nullable=False),
        sa.Column("effective_overall_pick", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("observed_counts_json", sa.Text(), nullable=False),
        sa.Column("target_ranges_json", sa.Text(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("explanation_template_key", sa.String(64), nullable=False),
        sa.Column("pivot_template_key", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("resolved_at", sa.String(32)),
        sa.CheckConstraint(
            "effective_overall_pick >= 1",
            name="ck_mock_guidance_event_effective_pick",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed')",
            name="ck_mock_guidance_event_status",
        ),
        sa.CheckConstraint(
            "state IN ("
            "'on_plan', 'watch', 'off_plan_viable', "
            "'risk_checkpoint', 'insufficient_evidence'"
            ")",
            name="ck_mock_guidance_event_state",
        ),
        sa.CheckConstraint(
            "confidence IN ('unavailable', 'low', 'medium', 'high')",
            name="ck_mock_guidance_event_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["mock_configuration_id"],
            ["mock_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_revision_id"],
            ["mock_strategy_revision.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "mock_configuration_id",
            "deterministic_event_key",
            name="uq_mock_guidance_event_key",
        ),
    )
    op.create_index(
        "ix_mock_guidance_event_configuration_pick",
        "mock_guidance_event",
        ["mock_configuration_id", "effective_overall_pick"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mock_guidance_event_configuration_pick",
        table_name="mock_guidance_event",
    )
    op.drop_table("mock_guidance_event")
    op.drop_index(
        "ix_mock_pick_decision_configuration_overall",
        table_name="mock_pick_decision",
    )
    op.drop_table("mock_pick_decision")
    op.drop_index(
        "ix_mock_cpu_profile_mock_configuration_id",
        table_name="mock_cpu_profile",
    )
    op.drop_table("mock_cpu_profile")
    op.drop_index(
        "ix_mock_strategy_revision_mock_configuration_id",
        table_name="mock_strategy_revision",
    )
    op.drop_table("mock_strategy_revision")
    op.drop_table("mock_configuration")
