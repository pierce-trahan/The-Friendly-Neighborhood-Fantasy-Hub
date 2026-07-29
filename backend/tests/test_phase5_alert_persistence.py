import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.engine import create_database_engine, sqlite_url
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPickValueSignalRow,
    AlertPlayerSignalRow,
    DraftAlertConfigurationRevisionRow,
    DraftAlertConfigurationRow,
    DraftAlertEvaluationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
)

ALERT_TABLES = {
    "alert_evidence_snapshot",
    "alert_player_signal",
    "alert_pick_value_signal",
    "draft_alert_configuration",
    "draft_alert_configuration_revision",
    "draft_alert_evaluation",
    "draft_alert_event",
    "draft_alert_trade_reference",
}
EVIDENCE_TABLES = {
    "alert_evidence_snapshot",
    "alert_player_signal",
    "alert_pick_value_signal",
}
NOW = "2026-07-28T00:00:00Z"
EXPECTED_COLUMNS = {
    "alert_evidence_snapshot": {
        "id",
        "schema_version",
        "source_label",
        "source_kind",
        "source_namespace",
        "permitted_use_confirmed",
        "private_source_reference",
        "format_json",
        "supported_draft_depth",
        "source_as_of",
        "imported_at",
        "content_hash",
        "status",
        "created_at",
    },
    "alert_player_signal": {
        "id",
        "evidence_snapshot_id",
        "player_id",
        "expected_pick_low",
        "expected_pick_high",
        "market_band",
        "win_now_production_band",
        "age_risk_band",
        "field_timestamps_json",
        "evidence_as_of",
        "limitation_codes_json",
        "private_source_record_reference",
    },
    "alert_pick_value_signal": {
        "id",
        "evidence_snapshot_id",
        "asset_key",
        "asset_type",
        "season_offset",
        "round_number",
        "overall_pick",
        "value_low",
        "value_high",
        "evidence_as_of",
        "limitation_codes_json",
    },
    "draft_alert_configuration": {
        "id",
        "draft_session_id",
        "evidence_snapshot_id",
        "enabled",
        "personal_qualifier_mode",
        "eligible_tier_count",
        "minimum_conservative_gap",
        "snooze_pick_count",
        "engine_version",
        "rule_version",
        "freshness_policy_version",
        "revision",
        "created_at",
        "updated_at",
    },
    "draft_alert_configuration_revision": {
        "id",
        "configuration_id",
        "sequence_number",
        "previous_evidence_snapshot_id",
        "next_evidence_snapshot_id",
        "previous_settings_json",
        "next_settings_json",
        "reason",
        "created_at",
    },
    "draft_alert_evaluation": {
        "id",
        "configuration_id",
        "draft_revision",
        "input_fingerprint",
        "current_overall_pick",
        "next_user_pick",
        "candidate_count",
        "opened_count",
        "updated_count",
        "superseded_count",
        "limitation_codes_json",
        "evaluated_at",
    },
    "draft_alert_event": {
        "id",
        "configuration_id",
        "player_id",
        "deterministic_event_key",
        "alert_kind",
        "status",
        "confidence",
        "freshness",
        "first_confirmed_draft_revision",
        "last_confirmed_draft_revision",
        "original_evidence_json",
        "current_evidence_json",
        "explanation_template_keys_json",
        "limitation_codes_json",
        "snooze_boundary",
        "dismissed_at",
        "superseded_at",
        "created_at",
        "updated_at",
    },
    "draft_alert_trade_reference": {
        "id",
        "event_id",
        "target_overall_pick_low",
        "target_overall_pick_high",
        "target_round_pick_labels_json",
        "cost_range_json",
        "pick_curve_snapshot_id",
        "explanation_template_key",
        "limitation_codes_json",
        "created_at",
    },
}
MODEL_ROWS = (
    AlertEvidenceSnapshotRow,
    AlertPlayerSignalRow,
    AlertPickValueSignalRow,
    DraftAlertConfigurationRow,
    DraftAlertConfigurationRevisionRow,
    DraftAlertEvaluationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
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
) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (
            index["name"],
            tuple(index["column_names"]),
            bool(index["unique"]),
        )
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
                    'board-1', 'Alert Persistence Board', NULL, NULL, 'overall',
                    0, :now, :now
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
                    'player-1', 'Fictional Receiver', 'Fictional', 'Receiver',
                    NULL, 'fictional receiver', 'TST', 'WR', '["WR"]', 'active',
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
                    'draft-1', 'Alert Persistence Draft', 'board-1', NULL, 'mock',
                    'snake', 1, 10, 24, 4, NULL, 'active', 3, NULL,
                    :now, :now, NULL, NULL
                )
                """
            ),
            {"now": NOW},
        )


def _seed_evidence_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO alert_evidence_snapshot (
                    id, schema_version, source_label, source_kind,
                    source_namespace, permitted_use_confirmed,
                    private_source_reference, format_json,
                    supported_draft_depth, source_as_of, imported_at,
                    content_hash, status, created_at
                ) VALUES (
                    'snapshot-1', 1, 'Fictional Fixture', 'synthetic',
                    'friendly_fixture', 1, NULL, '{}', 300, :now, :now,
                    :content_hash, 'committed', :now
                )
                """
            ),
            {"content_hash": "a" * 64, "now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO alert_player_signal (
                    id, evidence_snapshot_id, player_id, expected_pick_low,
                    expected_pick_high, market_band, win_now_production_band,
                    age_risk_band, field_timestamps_json, evidence_as_of,
                    limitation_codes_json, private_source_record_reference
                ) VALUES (
                    'signal-1', 'snapshot-1', 'player-1', 11, 15, 'strong',
                    'medium', 'lower', '{}', :now, '[]', NULL
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO alert_pick_value_signal (
                    id, evidence_snapshot_id, asset_key, asset_type,
                    season_offset, round_number, overall_pick, value_low,
                    value_high, evidence_as_of, limitation_codes_json
                ) VALUES (
                    'pick-value-1', 'snapshot-1', 'current.20',
                    'current_draft_pick', NULL, NULL, 20, 490, 510, :now, '[]'
                )
                """
            ),
            {"now": NOW},
        )


def _seed_draft_alert_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO draft_alert_configuration (
                    id, draft_session_id, evidence_snapshot_id, enabled,
                    personal_qualifier_mode, eligible_tier_count,
                    minimum_conservative_gap, snooze_pick_count, engine_version,
                    rule_version, freshness_policy_version, revision,
                    created_at, updated_at
                ) VALUES (
                    'config-1', 'draft-1', 'snapshot-1', 1,
                    'tier_or_favorite', 2, 6, 5, 'alert-engine-v1',
                    'alert-rules-v1', 'alert-freshness-v1', 0, :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_alert_configuration_revision (
                    id, configuration_id, sequence_number,
                    previous_evidence_snapshot_id, next_evidence_snapshot_id,
                    previous_settings_json, next_settings_json, reason, created_at
                ) VALUES (
                    'config-revision-1', 'config-1', 1, NULL, 'snapshot-1',
                    NULL, '{}', 'initial', :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_alert_evaluation (
                    id, configuration_id, draft_revision, input_fingerprint,
                    current_overall_pick, next_user_pick, candidate_count,
                    opened_count, updated_count, superseded_count,
                    limitation_codes_json, evaluated_at
                ) VALUES (
                    'evaluation-1', 'config-1', 3, :fingerprint, 21, 27, 8,
                    1, 0, 0, '[]', :now
                )
                """
            ),
            {"fingerprint": "b" * 64, "now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_alert_event (
                    id, configuration_id, player_id, deterministic_event_key,
                    alert_kind, status, confidence, freshness,
                    first_confirmed_draft_revision,
                    last_confirmed_draft_revision, original_evidence_json,
                    current_evidence_json, explanation_template_keys_json,
                    limitation_codes_json, snooze_boundary, dismissed_at,
                    superseded_at, created_at, updated_at
                ) VALUES (
                    'event-1', 'config-1', 'player-1', 'value:player-1',
                    'value_watch', 'open', 'high', 'fresh', 3, 3, '{}', '{}',
                    '["value_watch"]', '[]', NULL, NULL, NULL, :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO draft_alert_trade_reference (
                    id, event_id, target_overall_pick_low,
                    target_overall_pick_high, target_round_pick_labels_json,
                    cost_range_json, pick_curve_snapshot_id,
                    explanation_template_key, limitation_codes_json, created_at
                ) VALUES (
                    'trade-reference-1', 'event-1', 18, 20,
                    '["2.08", "2.10"]', '{}', 'snapshot-1',
                    'trade_up.pick_range', '[]', :now
                )
                """
            ),
            {"now": NOW},
        )


def test_alert_persistence_migration_round_trip(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "20260728_0007")
    engine = create_database_engine(runtime_settings.database_path)
    assert ALERT_TABLES.isdisjoint(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    assert ALERT_TABLES.issubset(inspect(engine).get_table_names())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        assert _column_names(engine, table_name) == expected_columns
    for row_type in MODEL_ROWS:
        table_name = row_type.__tablename__
        assert set(row_type.__table__.columns.keys()) == EXPECTED_COLUMNS[table_name]
        model_indexes = {
            (
                index.name,
                tuple(column.name for column in index.columns),
                index.unique,
            )
            for index in row_type.__table__.indexes
        }
        assert _index_definitions(engine, table_name) == model_indexes
        model_checks = {
            constraint.name
            for constraint in row_type.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and isinstance(constraint.name, str)
        }
        assert _check_constraint_names(engine, table_name) == model_checks

    assert ("content_hash",) in _unique_column_sets(
        engine,
        "alert_evidence_snapshot",
    )
    assert ("evidence_snapshot_id", "player_id") in _unique_column_sets(
        engine,
        "alert_player_signal",
    )
    assert ("evidence_snapshot_id", "asset_key") in _unique_column_sets(
        engine,
        "alert_pick_value_signal",
    )
    assert ("draft_session_id",) in _unique_column_sets(
        engine,
        "draft_alert_configuration",
    )
    assert ("configuration_id", "sequence_number") in _unique_column_sets(
        engine,
        "draft_alert_configuration_revision",
    )
    assert ("configuration_id", "input_fingerprint") in _unique_column_sets(
        engine,
        "draft_alert_evaluation",
    )
    assert ("configuration_id", "deterministic_event_key") in _unique_column_sets(
        engine,
        "draft_alert_event",
    )
    assert (
        _foreign_key_ondelete(
            engine,
            "draft_alert_configuration",
            "draft_session_id",
        )
        == "CASCADE"
    )
    for table_name in (
        "draft_alert_configuration_revision",
        "draft_alert_evaluation",
        "draft_alert_event",
    ):
        assert (
            _foreign_key_ondelete(engine, table_name, "configuration_id")
            == "CASCADE"
        )
    assert (
        _foreign_key_ondelete(
            engine,
            "draft_alert_trade_reference",
            "event_id",
        )
        == "CASCADE"
    )
    with engine.connect() as connection:
        trigger_names = set(
            connection.execute(
                text(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'trigger' AND name LIKE 'trg_alert_%'
                    """
                )
            ).scalars()
        )
    assert len(trigger_names) == 6
    engine.dispose()

    command.downgrade(config, "20260728_0007")
    engine = create_database_engine(runtime_settings.database_path)
    assert ALERT_TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20260728_0007"
        )
    engine.dispose()
    command.upgrade(config, "head")


def test_alert_evidence_is_immutable_and_draft_rows_cascade(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _seed_evidence_rows(engine)
    _seed_draft_alert_rows(engine)

    immutable_statements = (
        "UPDATE alert_evidence_snapshot SET status = 'superseded' "
        "WHERE id = 'snapshot-1'",
        "UPDATE alert_player_signal SET expected_pick_low = 12 "
        "WHERE id = 'signal-1'",
        "DELETE FROM alert_pick_value_signal WHERE id = 'pick-value-1'",
    )
    for statement in immutable_statements:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM draft_session WHERE id = 'draft-1'"))

    with engine.connect() as connection:
        for table_name in ALERT_TABLES - EVIDENCE_TABLES:
            assert connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one() == 0
        for table_name in EVIDENCE_TABLES:
            assert connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM player WHERE id = 'player-1'")
        ).scalar_one() == 1
    engine.dispose()


def test_alert_persistence_constraints_and_uniqueness(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _seed_evidence_rows(engine)
    _seed_draft_alert_rows(engine)

    invalid_statements = (
        """
        INSERT INTO alert_player_signal (
            id, evidence_snapshot_id, player_id, expected_pick_low,
            expected_pick_high, market_band, win_now_production_band,
            age_risk_band, field_timestamps_json, evidence_as_of,
            limitation_codes_json, private_source_record_reference
        ) VALUES (
            'signal-duplicate', 'snapshot-1', 'player-1', 11, 15, NULL,
            NULL, NULL, '{}', '2026-07-28T00:00:00Z', '[]', NULL
        )
        """,
        """
        INSERT INTO alert_pick_value_signal (
            id, evidence_snapshot_id, asset_key, asset_type, season_offset,
            round_number, overall_pick, value_low, value_high, evidence_as_of,
            limitation_codes_json
        ) VALUES (
            'pick-value-duplicate', 'snapshot-1', 'different-key',
            'current_draft_pick', NULL, NULL, 20, 400, 500,
            '2026-07-28T00:00:00Z', '[]'
        )
        """,
        """
        INSERT INTO alert_pick_value_signal (
            id, evidence_snapshot_id, asset_key, asset_type, season_offset,
            round_number, overall_pick, value_low, value_high, evidence_as_of,
            limitation_codes_json
        ) VALUES (
            'pick-value-invalid', 'snapshot-1', 'future.bad', 'future_round',
            NULL, 2, NULL, 500, 400, '2026-07-28T00:00:00Z', '[]'
        )
        """,
        "UPDATE draft_alert_configuration SET personal_qualifier_mode = 'all' "
        "WHERE id = 'config-1'",
        """
        INSERT INTO draft_alert_configuration_revision (
            id, configuration_id, sequence_number,
            previous_evidence_snapshot_id, next_evidence_snapshot_id,
            previous_settings_json, next_settings_json, reason, created_at
        ) VALUES (
            'config-revision-duplicate', 'config-1', 1, NULL, 'snapshot-1',
            NULL, '{}', 'initial', '2026-07-28T00:00:00Z'
        )
        """,
        """
        INSERT INTO draft_alert_evaluation (
            id, configuration_id, draft_revision, input_fingerprint,
            current_overall_pick, next_user_pick, candidate_count, opened_count,
            updated_count, superseded_count, limitation_codes_json, evaluated_at
        ) VALUES (
            'evaluation-duplicate', 'config-1', 4,
            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
            22, 27, 8, 0, 1, 0, '[]', '2026-07-28T00:00:00Z'
        )
        """,
        "UPDATE draft_alert_event SET status = 'hidden' WHERE id = 'event-1'",
        "UPDATE draft_alert_event SET last_confirmed_draft_revision = 2 "
        "WHERE id = 'event-1'",
        "UPDATE draft_alert_trade_reference SET target_overall_pick_low = 21 "
        "WHERE id = 'trade-reference-1'",
    )
    for statement in invalid_statements:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))
    engine.dispose()


def test_alert_import_transaction_rolls_back_on_late_failure(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO alert_evidence_snapshot (
                        id, schema_version, source_label, source_kind,
                        source_namespace, permitted_use_confirmed,
                        private_source_reference, format_json,
                        supported_draft_depth, source_as_of, imported_at,
                        content_hash, status, created_at
                    ) VALUES (
                        'snapshot-rollback', 1, 'Rollback Fixture', 'synthetic',
                        'rollback_fixture', 1, NULL, '{}', 300, :now, :now,
                        :content_hash, 'committed', :now
                    )
                    """
                ),
                {"content_hash": "c" * 64, "now": NOW},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO alert_player_signal (
                        id, evidence_snapshot_id, player_id, expected_pick_low,
                        expected_pick_high, market_band,
                        win_now_production_band, age_risk_band,
                        field_timestamps_json, evidence_as_of,
                        limitation_codes_json, private_source_record_reference
                    ) VALUES (
                        'signal-rollback', 'snapshot-rollback', 'player-1',
                        10, 12, NULL, NULL, NULL, '{}', :now, '[]', NULL
                    )
                    """
                ),
                {"now": NOW},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO alert_pick_value_signal (
                        id, evidence_snapshot_id, asset_key, asset_type,
                        season_offset, round_number, overall_pick, value_low,
                        value_high, evidence_as_of, limitation_codes_json
                    ) VALUES (
                        'pick-value-rollback', 'snapshot-rollback', 'bad-range',
                        'current_draft_pick', NULL, NULL, 24, 700, 600,
                        :now, '[]'
                    )
                    """
                ),
                {"now": NOW},
            )

    with engine.connect() as connection:
        for table_name in EVIDENCE_TABLES:
            assert connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one() == 0
    engine.dispose()
