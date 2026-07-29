import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.engine import (
    create_database_engine,
    create_session_factory,
    sqlite_url,
)
from friendly_hub.domains.reports.models import (
    PostDraftReportMomentRow,
    PostDraftReportPlayerRow,
    PostDraftReportRow,
    PostDraftReportSectionRow,
)

REPORT_TABLES = {
    "post_draft_report",
    "post_draft_report_player",
    "post_draft_report_section",
    "post_draft_report_moment",
}
NOW = "2026-07-29T20:00:00Z"
EXPECTED_COLUMNS = {
    "post_draft_report": {
        "id",
        "draft_session_id",
        "draft_revision",
        "input_fingerprint",
        "league_shape_fingerprint",
        "report_engine_version",
        "report_rules_version",
        "explanation_template_version",
        "draft_mode",
        "generated_at",
        "completed_at",
        "section_summary_json",
        "limitation_codes_json",
    },
    "post_draft_report_player": {
        "id",
        "report_id",
        "player_id",
        "overall_pick",
        "round_number",
        "primary_position",
        "fantasy_positions_json",
        "starter_assignment",
        "saved_personal_rank",
        "saved_tier_order",
        "saved_favorite",
        "safe_evidence_json",
    },
    "post_draft_report_section": {
        "id",
        "report_id",
        "section_key",
        "availability",
        "confidence",
        "metrics_json",
        "reason_codes_json",
        "limitation_codes_json",
        "explanation_template_key",
        "explanation",
        "safe_provenance_json",
    },
    "post_draft_report_moment": {
        "id",
        "report_id",
        "moment_key",
        "moment_kind",
        "overall_pick",
        "primary_player_id",
        "secondary_player_id",
        "safe_summary_json",
        "reason_codes_json",
        "limitation_codes_json",
    },
}
MODEL_ROWS = (
    PostDraftReportRow,
    PostDraftReportPlayerRow,
    PostDraftReportSectionRow,
    PostDraftReportMomentRow,
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
                    'board-1', 'Report Persistence Board', NULL, NULL, 'overall',
                    0, :now, :now
                )
                """
            ),
            {"now": NOW},
        )
        for player_id, display_name, position in (
            ("player-1", "Fictional Quarterback", "QB"),
            ("player-2", "Fictional Receiver", "WR"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO player (
                        id, display_name, first_name, last_name, suffix,
                        search_name, team, primary_position,
                        fantasy_positions_json, status, rookie_class, is_rookie,
                        created_at, updated_at
                    ) VALUES (
                        :player_id, :display_name, 'Fictional', 'Player', NULL,
                        :search_name, 'TST', :position, :positions, 'active',
                        NULL, 0, :now, :now
                    )
                    """
                ),
                {
                    "display_name": display_name,
                    "now": NOW,
                    "player_id": player_id,
                    "position": position,
                    "positions": f'["{position}"]',
                    "search_name": display_name.casefold(),
                },
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
                    'draft-1', 'Completed Fictional Draft', 'board-1', NULL,
                    'mock', 'snake', 1, 10, 24, 4, NULL, 'completed', 240,
                    NULL, :now, :now, :now, NULL
                )
                """
            ),
            {"now": NOW},
        )


def _persist_report_rows(engine: Engine) -> None:
    session_factory = create_session_factory(engine)
    with session_factory.begin() as session:
        session.add(
            PostDraftReportRow(
                id="report-1",
                draft_session_id="draft-1",
                draft_revision=240,
                input_fingerprint="a" * 64,
                league_shape_fingerprint="b" * 64,
                report_engine_version="post-draft-report-engine-v1",
                report_rules_version="post-draft-report-rules-v1",
                explanation_template_version="post-draft-report-explanations-v1",
                draft_mode="mock",
                generated_at=NOW,
                completed_at=NOW,
                section_summary_json='{"supported":1}',
                limitation_codes_json="[]",
            )
        )
        session.flush()
        session.add_all(
            (
                PostDraftReportPlayerRow(
                    id="report-player-1",
                    report_id="report-1",
                    player_id="player-1",
                    overall_pick=7,
                    round_number=1,
                    primary_position="QB",
                    fantasy_positions_json='["QB"]',
                    starter_assignment="QB1",
                    saved_personal_rank=3,
                    saved_tier_order=1,
                    saved_favorite=True,
                    safe_evidence_json="{}",
                ),
                PostDraftReportSectionRow(
                    id="report-section-1",
                    report_id="report-1",
                    section_key="starter_coverage",
                    availability="supported",
                    confidence="high",
                    metrics_json='{"filled":8}',
                    reason_codes_json='["STARTER_ASSIGNMENT_COMPLETE"]',
                    limitation_codes_json="[]",
                    explanation_template_key="starter.coverage_complete",
                    explanation=(
                        "All 8 configured starter slots can be covered by the "
                        "drafted roster."
                    ),
                    safe_provenance_json="{}",
                ),
                PostDraftReportMomentRow(
                    id="report-moment-1",
                    report_id="report-1",
                    moment_key="personal-board:7:player-1",
                    moment_kind="personal_board_choice",
                    overall_pick=7,
                    primary_player_id="player-1",
                    secondary_player_id="player-2",
                    safe_summary_json='{"rank_delta":5}',
                    reason_codes_json='["PERSONAL_BOARD_OBSERVATION_ONLY"]',
                    limitation_codes_json="[]",
                ),
            )
        )


def test_report_persistence_migration_round_trip(
    runtime_settings: RuntimeSettings,
) -> None:
    config = _alembic_config(runtime_settings)
    command.upgrade(config, "20260728_0008")
    engine = create_database_engine(runtime_settings.database_path)
    assert REPORT_TABLES.isdisjoint(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_database_engine(runtime_settings.database_path)
    assert REPORT_TABLES.issubset(inspect(engine).get_table_names())
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

    assert ("draft_session_id", "input_fingerprint") in _unique_column_sets(
        engine,
        "post_draft_report",
    )
    assert {
        ("report_id", "player_id"),
        ("report_id", "overall_pick"),
    }.issubset(_unique_column_sets(engine, "post_draft_report_player"))
    assert ("report_id", "section_key") in _unique_column_sets(
        engine,
        "post_draft_report_section",
    )
    assert ("report_id", "moment_key") in _unique_column_sets(
        engine,
        "post_draft_report_moment",
    )
    assert (
        _foreign_key_ondelete(
            engine,
            "post_draft_report",
            "draft_session_id",
        )
        == "CASCADE"
    )
    for table_name in REPORT_TABLES - {"post_draft_report"}:
        assert _foreign_key_ondelete(engine, table_name, "report_id") == "CASCADE"
    with engine.connect() as connection:
        trigger_names = set(
            connection.execute(
                text(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'trigger'
                      AND name LIKE 'trg_post_draft_report%'
                    """
                )
            ).scalars()
        )
    assert len(trigger_names) == 8
    engine.dispose()

    command.downgrade(config, "20260728_0008")
    engine = create_database_engine(runtime_settings.database_path)
    assert REPORT_TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version"))
            .scalar_one()
            == "20260728_0008"
        )
    engine.dispose()
    command.upgrade(config, "head")


def test_report_models_round_trip_and_rows_are_immutable(
    runtime_settings: RuntimeSettings,
) -> None:
    command.upgrade(_alembic_config(runtime_settings), "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _persist_report_rows(engine)

    session_factory = create_session_factory(engine)
    with session_factory() as session:
        report = session.get(PostDraftReportRow, "report-1")
        assert report is not None
        assert report.draft_revision == 240
        assert report.input_fingerprint == "a" * 64
        assert session.scalar(
            select(PostDraftReportPlayerRow).where(
                PostDraftReportPlayerRow.report_id == report.id
            )
        ).starter_assignment == "QB1"
        assert session.scalar(
            select(PostDraftReportSectionRow).where(
                PostDraftReportSectionRow.report_id == report.id
            )
        ).availability == "supported"
        assert session.scalar(
            select(PostDraftReportMomentRow).where(
                PostDraftReportMomentRow.report_id == report.id
            )
        ).moment_kind == "personal_board_choice"

    immutable_statements = (
        "UPDATE post_draft_report SET draft_revision = 241 WHERE id = 'report-1'",
        "UPDATE post_draft_report_player SET overall_pick = 8 "
        "WHERE id = 'report-player-1'",
        "DELETE FROM post_draft_report_section WHERE id = 'report-section-1'",
        "DELETE FROM post_draft_report WHERE id = 'report-1'",
    )
    for statement in immutable_statements:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))
    engine.dispose()


def test_reset_preserves_report_and_source_draft_delete_cascades(
    runtime_settings: RuntimeSettings,
) -> None:
    command.upgrade(_alembic_config(runtime_settings), "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _persist_report_rows(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO draft_session (
                    id, name, board_id, league_profile_id, mode, draft_format,
                    third_round_reversal, team_count, round_count, user_slot,
                    pick_timer_seconds, status, revision, reset_from_session_id,
                    created_at, updated_at, completed_at, reset_at
                ) VALUES (
                    'draft-reset', 'Reset Draft', 'board-1', NULL, 'mock',
                    'snake', 1, 10, 24, 4, NULL, 'active', 0, 'draft-1',
                    :now, :now, NULL, NULL
                )
                """
            ),
            {"now": NOW},
        )
        connection.execute(
            text("DELETE FROM draft_session WHERE id = 'draft-reset'")
        )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM post_draft_report")
        ).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM draft_session WHERE id = 'draft-1'"))
    with engine.connect() as connection:
        for table_name in REPORT_TABLES:
            assert connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM player")
        ).scalar_one() == 2
        assert connection.execute(
            text("SELECT COUNT(*) FROM personal_board")
        ).scalar_one() == 1
    engine.dispose()


def test_report_persistence_constraints_reject_invalid_or_duplicate_rows(
    runtime_settings: RuntimeSettings,
) -> None:
    command.upgrade(_alembic_config(runtime_settings), "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)
    _persist_report_rows(engine)

    invalid_statements = (
        f"""
        INSERT INTO post_draft_report (
            id, draft_session_id, draft_revision, input_fingerprint,
            league_shape_fingerprint, report_engine_version,
            report_rules_version, explanation_template_version, draft_mode,
            generated_at, completed_at, section_summary_json,
            limitation_codes_json
        ) VALUES (
            'report-duplicate', 'draft-1', 240, '{"a" * 64}', '{"c" * 64}',
            'engine-v1', 'rules-v1', 'explanations-v1', 'mock', '{NOW}', '{NOW}',
            '{{}}', '[]'
        )
        """,
        f"""
        INSERT INTO post_draft_report (
            id, draft_session_id, draft_revision, input_fingerprint,
            league_shape_fingerprint, report_engine_version,
            report_rules_version, explanation_template_version, draft_mode,
            generated_at, completed_at, section_summary_json,
            limitation_codes_json
        ) VALUES (
            'report-uppercase', 'draft-1', 240, '{"C" * 64}', '{"d" * 64}',
            'engine-v1', 'rules-v1', 'explanations-v1', 'mock', '{NOW}', '{NOW}',
            '{{}}', '[]'
        )
        """,
        """
        INSERT INTO post_draft_report_player (
            id, report_id, player_id, overall_pick, round_number,
            primary_position, fantasy_positions_json, starter_assignment,
            saved_personal_rank, saved_tier_order, saved_favorite,
            safe_evidence_json
        ) VALUES (
            'report-player-duplicate', 'report-1', 'player-1', 8, 1, 'QB',
            '["QB"]', NULL, NULL, NULL, 0, '{}'
        )
        """,
        """
        INSERT INTO post_draft_report_player (
            id, report_id, player_id, overall_pick, round_number,
            primary_position, fantasy_positions_json, starter_assignment,
            saved_personal_rank, saved_tier_order, saved_favorite,
            safe_evidence_json
        ) VALUES (
            'report-pick-duplicate', 'report-1', 'player-2', 7, 1, 'WR',
            '["WR"]', NULL, NULL, NULL, 0, '{}'
        )
        """,
        """
        INSERT INTO post_draft_report_section (
            id, report_id, section_key, availability, confidence, metrics_json,
            reason_codes_json, limitation_codes_json,
            explanation_template_key, explanation, safe_provenance_json
        ) VALUES (
            'section-invalid-state', 'report-1', 'position_inventory', 'graded',
            'high', '{}', '[]', '[]', 'position.summary', 'Summary', '{}'
        )
        """,
        """
        INSERT INTO post_draft_report_section (
            id, report_id, section_key, availability, confidence, metrics_json,
            reason_codes_json, limitation_codes_json,
            explanation_template_key, explanation, safe_provenance_json
        ) VALUES (
            'section-invalid-json', 'report-1', 'draft_summary', 'supported',
            'high', '{bad}', '[]', '[]', 'draft.summary', 'Summary', '{}'
        )
        """,
        """
        INSERT INTO post_draft_report_moment (
            id, report_id, moment_key, moment_kind, overall_pick,
            primary_player_id, secondary_player_id, safe_summary_json,
            reason_codes_json, limitation_codes_json
        ) VALUES (
            'moment-invalid-kind', 'report-1', 'invalid-kind', 'hindsight', 8,
            'player-1', NULL, '{}', '[]', '[]'
        )
        """,
        """
        INSERT INTO post_draft_report_moment (
            id, report_id, moment_key, moment_kind, overall_pick,
            primary_player_id, secondary_player_id, safe_summary_json,
            reason_codes_json, limitation_codes_json
        ) VALUES (
            'moment-duplicate', 'report-1', 'personal-board:7:player-1',
            'personal_board_choice', 8, 'player-1', NULL, '{}', '[]', '[]'
        )
        """,
    )
    for statement in invalid_statements:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement))
    engine.dispose()


def test_report_transaction_rolls_back_on_late_failure(
    runtime_settings: RuntimeSettings,
) -> None:
    command.upgrade(_alembic_config(runtime_settings), "head")
    engine = create_database_engine(runtime_settings.database_path)
    _seed_parent_rows(engine)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO post_draft_report (
                        id, draft_session_id, draft_revision, input_fingerprint,
                        league_shape_fingerprint, report_engine_version,
                        report_rules_version, explanation_template_version,
                        draft_mode, generated_at, completed_at,
                        section_summary_json, limitation_codes_json
                    ) VALUES (
                        'report-rollback', 'draft-1', 240, :input_fingerprint,
                        :league_fingerprint, 'post-draft-report-engine-v1',
                        'post-draft-report-rules-v1',
                        'post-draft-report-explanations-v1', 'mock', :now, :now,
                        '{}', '[]'
                    )
                    """
                ),
                {
                    "input_fingerprint": "e" * 64,
                    "league_fingerprint": "f" * 64,
                    "now": NOW,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO post_draft_report_player (
                        id, report_id, player_id, overall_pick, round_number,
                        primary_position, fantasy_positions_json,
                        starter_assignment, saved_personal_rank, saved_tier_order,
                        saved_favorite, safe_evidence_json
                    ) VALUES (
                        'player-rollback', 'report-rollback', 'player-1', 7, 1,
                        'QB', '["QB"]', 'QB1', 3, 1, 1, '{}'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO post_draft_report_section (
                        id, report_id, section_key, availability, confidence,
                        metrics_json, reason_codes_json, limitation_codes_json,
                        explanation_template_key, explanation,
                        safe_provenance_json
                    ) VALUES (
                        'section-rollback', 'report-rollback',
                        'starter_coverage', 'supported', 'certain', '{}', '[]',
                        '[]', 'starter.coverage_complete', 'Complete', '{}'
                    )
                    """
                )
            )

    with engine.connect() as connection:
        for table_name in REPORT_TABLES:
            assert connection.execute(
                text(
                    f"SELECT COUNT(*) FROM {table_name} "
                    "WHERE id LIKE '%rollback%'"
                )
            ).scalar_one() == 0
    engine.dispose()
