from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from friendly_hub.db.base import Base
from friendly_hub.domains.boards.models import (  # noqa: F401
    BoardEntryRow,
    BoardTierRow,
    PersonalBoardRow,
)
from friendly_hub.domains.configuration.models import AppConfigurationRow  # noqa: F401
from friendly_hub.domains.drafts.models import (  # noqa: F401
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
    DraftTeamRow,
)
from friendly_hub.domains.gut_elo.models import (  # noqa: F401
    GutEloActionRow,
    GutEloParticipantRow,
    GutEloSessionRow,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow  # noqa: F401
from friendly_hub.domains.mocks.models import (  # noqa: F401
    MockConfigurationRow,
    MockCpuProfileRow,
    MockGuidanceEventRow,
    MockPickDecisionRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.players.models import (  # noqa: F401
    PlayerExternalIdRow,
    PlayerImportRow,
    PlayerImportSessionRow,
    PlayerMappingDecisionRow,
    PlayerRelevanceRow,
    PlayerRow,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
