import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Engine, String, inspect, text
from sqlalchemy.exc import IntegrityError

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.engine import create_database_engine, sqlite_url
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockCpuProfileRow,
    MockGuidanceEventRow,
    MockPickDecisionRow,
    MockStrategyRevisionRow,
)

MOCK_TABLES = {
    "mock_configuration",
    "mock_strategy_revision",
    "mock_cpu_profile",
    "mock_pick_decision",
    "mock_guidance_event",
}
NOW = "2026-07-28T00:00:00Z"
EXPECTED_COLUMNS = {
    "mock_configuration": {
        "id",
        "draft_session_id",
        "seed",
        "rng_version",
        "cpu_engine_version",
        "strategy_definition_version",
        "league_shape_json",
        "league_shape_source_timestamp",
        "content_fingerprint",
        "randomness",
        "current_strategy_key",
        "revision",
        "include_in_learning",
        "learning_opted_in_at",
        "learning_withdrawn_at",
        "created_at",
        "updated_at",
    },
    "mock_strategy_revision": {
        "id",
        "mock_configuration_id",
        "sequence_number",
        "previous_strategy_key",
        "next_strategy_key",
        "effective_overall_pick",
        "user_roster_counts_json",
        "private_user_note",
        "created_at",
    },
    "mock_cpu_profile": {
        "id",
        "mock_configuration_id",
        "draft_slot",
        "source",
        "archetype_key",
        "confidence",
        "draft_sample_count",
        "pick_sample_count",
        "tendency_snapshot_json",
        "internal_manager_reference",
        "source_timestamp",
        "created_at",
    },
    "mock_pick_decision": {
        "id",
        "mock_configuration_id",
        "draft_pick_revision_id",
        "overall_pick",
        "selecting_slot",
        "chosen_player_id",
        "profile_source",
        "profile_archetype_key",
        "engine_version",
        "rng_version",
        "total_score",
        "component_scores_json",
        "random_audit_json",
        "alternatives_json",
        "reason_codes_json",
        "limitation_codes_json",
        "created_at",
    },
    "mock_guidance_event": {
        "id",
        "mock_configuration_id",
        "strategy_revision_id",
        "deterministic_event_key",
        "effective_overall_pick",
        "state",
        "confidence",
        "observed_counts_json",
        "target_ranges_json",
        "reason_codes_json",
        "limitation_codes_json",
        "explanation_template_key",
        "pivot_template_key",
        "status",
        "created_at",
        "resolved_at",
    },
}
MODEL_ROWS = (
    MockConfigurationRow,
    MockStrategyRevisionRow,
    MockCpuProfileRow,
    MockPickDecisionRow,
    MockGuidanceEventRow,
)


def _alembic_config(settings: RuntimeSettings) -> Config:
    settings.ensure_directories()
    backend_root = settings.project_root / "backend"
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlite_url(settings.database_path))
    return config


def _column_names(engine: Engine, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in inspect(engine).get_columns(table_name)
        if isinstance(column["name"], str)
    }


def _unique_column_sets(engine: Engine, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints(table_name)
    }


def _index_definitions(
    engine: Engine,
    table_name: str,
) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (index["name"], tuple(index["column_names"]))
        for index in inspect(engine).get_indexes(table_name)
    }


def _check_constraint_names(engine: Engine, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspect(engine).get_check_constraints(table_name)
        if isinstance(constraint["name"], str)
    }


def _foreign_key_ondelete(
    engine: Engine,
    table_name: str,
    constrained_column: str,
) -> str | None:
    for foreign_key in inspect(engine).get_foreign_keys(table_name):
        if foreign_key["constrained_columns"] == [constrained_column]:
            return foreign_key["options"].get("ondelete")
    raise AssertionError(f"Missing foreign key for {table_name}.{constrained_column}")


def _seed_parent_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO personal_board (
                    id, name, description, league_profile_id, scope, archived,
                    created_at, updated_at
                ) VALUES (
                    'board-1', 'Persistence Board', NULL, NULL, 'overall', 0,
                    :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO player (
                    id, display_name, first_name, last_name, suffix, search_name,
                    team, primary_position, fantasy_positions_json, status,
                    rookie_class, is_rookie, created_at, updated_at
                ) VALUES (
                    'player-1', 'Test Player', 'Test', 'Player', NULL,
                    'test player', NULL, 'WR', '["WR"]', 'active',
                    NULL, 0, :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_session (
                    id, name, board_id, league_profile_id, mode, draft_format,
                    third_round_reversal, team_count, round_count, user_slot,
                    pick_timer_seconds, status, revision, reset_from_session_id,
                    created_at, updated_at, completed_at, reset_at
                ) VALUES (
                    'draft-1', 'Persistence Mock', 'board-1', NULL, 'mock',
                    'snake', 1, 10, 24, 4, NULL, 'active', 1, NULL,
                    :now, :now, NULL, NULL
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_pick (
                    id, session_id, overall_pick, round_number, pick_in_round,
                    selecting_slot, player_id, recorded_at, client_entered_at,
                    correction_count
                ) VALUES (
                    'pick-1', 'draft-1', 1, 1, 1, 1, 'player-1',
                    :now, NULL, 0
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_pick_revision (
                    id, session_id, pick_id, session_revision, action_kind,
                    previous_player_id, next_player_id, created_at
                ) VALUES (
                    'pick-revision-1', 'draft-1', 'pick-1', 1, 'made',
                    NULL, 'player-1', :now
                )
                """
            ),
            {"now": NOW},
        )


def _seed_mock_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO mock_configuration (
                    id, draft_session_id, seed, rng_version, cpu_engine_version,
                    strategy_definition_version, league_shape_json,
                    league_shape_source_timestamp, content_fingerprint,
                    randomness, current_strategy_key, revision,
                    include_in_learning, learning_opted_in_at,
                    learning_withdrawn_at, created_at, updated_at
                ) VALUES (
                    'mock-1', 'draft-1', '42', 'sha256-counter-v1',
                    'practice-board-v1', 'strategy-v1', '{}', NULL,
                    :fingerprint, 35, 'balanced', 0, 0, NULL, NULL, :now, :now
                )
                """
            ),
            {"fingerprint": "a" * 64, "now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO mock_strategy_revision (
                    id, mock_configuration_id, sequence_number,
                    previous_strategy_key, next_strategy_key,
                    effective_overall_pick, user_roster_counts_json,
                    private_user_note, created_at
                ) VALUES (
                    'strategy-1', 'mock-1', 1, NULL, 'balanced', 1,
                    '{}', 'private local note', :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO mock_cpu_profile (
                    id, mock_configuration_id, draft_slot, source,
                    archetype_key, confidence, draft_sample_count,
                    pick_sample_count, tendency_snapshot_json,
                    internal_manager_reference, source_timestamp, created_at
                ) VALUES (
                    'profile-1', 'mock-1', 1, 'fallback', 'balanced',
                    'not_applicable', 0, 0, '{}', NULL, :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO mock_pick_decision (
                    id, mock_configuration_id, draft_pick_revision_id,
                    overall_pick, selecting_slot, chosen_player_id,
                    profile_source, profile_archetype_key, engine_version,
                    rng_version, total_score, component_scores_json,
                    random_audit_json, alternatives_json, reason_codes_json,
                    limitation_codes_json, created_at
                ) VALUES (
                    'decision-1', 'mock-1', 'pick-revision-1', 1, 1,
                    'player-1', 'fallback', 'balanced', 'practice-board-v1',
                    'sha256-counter-v1', 100, '{}', '{}', '[]', '[]', '[]',
                    :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO mock_guidance_event (
                    id, mock_configuration_id, strategy_revision_id,
                    deterministic_event_key, effective_overall_pick, state,
                    confidence, observed_counts_json, target_ranges_json,
                    reason_codes_json, limitation_codes_json,
                    explanation_template_key, pivot_template_key, status,
                    created_at, resolved_at
                ) VALUES (
                    'guidance-1', 'mock-1', 'strategy-1', 'balanced:early:1',
                    1, 'on_plan', 'high', '{}', '{}', '[]', '[]',
                    'balanced.early.on_plan', NULL, 'open', :now, NULL
                )
                """
            ),
            {"now": NOW},
        )


def test_mock_persistence_migration_round_trip(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "20260728_0006")
    engine = create_database_engine(runtime_settings.database_path)
    assert MOCK_TABLES.isdisjoint(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    inspector = inspect(engine)
    assert MOCK_TABLES.issubset(inspector.get_table_names())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        assert _column_names(engine, table_name) == expected_columns
    for row_type in MODEL_ROWS:
        assert set(row_type.__table__.columns.keys()) == EXPECTED_COLUMNS[
            row_type.__tablename__
        ]
        model_indexes = {
            (index.name, tuple(column.name for column in index.columns))
            for index in row_type.__table__.indexes
        }
        assert _index_definitions(engine, row_type.__tablename__) == model_indexes
        model_check_names = {
            constraint.name
            for constraint in row_type.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and isinstance(constraint.name, str)
        }
        assert (
            _check_constraint_names(engine, row_type.__tablename__)
            == model_check_names
        )
    profile_columns = {
        column["name"]: column
        for column in inspector.get_columns("mock_cpu_profile")
    }
    guidance_columns = {
        column["name"]: column
        for column in inspector.get_columns("mock_guidance_event")
    }
    assert isinstance(profile_columns["confidence"]["type"], String)
    assert isinstance(guidance_columns["confidence"]["type"], String)
    assert ("draft_session_id",) in _unique_column_sets(
        engine,
        "mock_configuration",
    )
    assert ("mock_configuration_id", "sequence_number") in _unique_column_sets(
        engine,
        "mock_strategy_revision",
    )
    assert ("mock_configuration_id", "draft_slot") in _unique_column_sets(
        engine,
        "mock_cpu_profile",
    )
    assert ("draft_pick_revision_id",) in _unique_column_sets(
        engine,
        "mock_pick_decision",
    )
    assert (
        "mock_configuration_id",
        "deterministic_event_key",
    ) in _unique_column_sets(engine, "mock_guidance_event")
    assert (
        _foreign_key_ondelete(
            engine,
            "mock_configuration",
            "draft_session_id",
        )
        == "CASCADE"
    )
    for table_name in (
        "mock_strategy_revision",
        "mock_cpu_profile",
        "mock_pick_decision",
        "mock_guidance_event",
    ):
        assert (
            _foreign_key_ondelete(
                engine,
                table_name,
                "mock_configuration_id",
            )
            == "CASCADE"
        )
    assert (
        _foreign_key_ondelete(
            engine,
            "mock_pick_decision",
            "draft_pick_revision_id",
        )
        == "CASCADE"
    )
    assert (
        _foreign_key_ondelete(
            engine,
            "mock_guidance_event",
            "strategy_revision_id",
        )
        == "CASCADE"
    )
    engine.dispose()

    command.downgrade(config, "20260728_0006")
    engine = create_database_engine(runtime_settings.database_path)
    assert MOCK_TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20260728_0006"
        )
    engine.dispose()

    command.upgrade(config, "head")


def test_mock_persistence_constraints_and_cascade(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _seed_mock_rows(engine)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO mock_strategy_revision (
                        id, mock_configuration_id, sequence_number,
                        previous_strategy_key, next_strategy_key,
                        effective_overall_pick, user_roster_counts_json,
                        private_user_note, created_at
                    ) VALUES (
                        'strategy-duplicate', 'mock-1', 1, NULL, 'hero_rb',
                        2, '{}', NULL, :now
                    )
                    """
                ),
                {"now": NOW},
            )

    invalid_updates = (
        "UPDATE mock_configuration SET randomness = 101 WHERE id = 'mock-1'",
        "UPDATE mock_cpu_profile SET source = 'unknown' WHERE id = 'profile-1'",
        "UPDATE mock_cpu_profile SET confidence = 'unavailable' WHERE id = 'profile-1'",
        "UPDATE mock_cpu_profile SET source = 'history', confidence = 'low' "
        "WHERE id = 'profile-1'",
        "UPDATE mock_pick_decision SET profile_source = 'unknown' "
        "WHERE id = 'decision-1'",
        "UPDATE mock_guidance_event SET state = 'locked' WHERE id = 'guidance-1'",
        "UPDATE mock_guidance_event SET confidence = 'not_applicable' "
        "WHERE id = 'guidance-1'",
        "UPDATE mock_guidance_event SET status = 'hidden' WHERE id = 'guidance-1'",
    )
    for statement in invalid_updates:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM draft_session WHERE id = 'draft-1'")
        )
    with engine.connect() as connection:
        for table_name in MOCK_TABLES:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one()
            assert count == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM player WHERE id = 'player-1'")
        ).scalar_one() == 1
    engine.dispose()
