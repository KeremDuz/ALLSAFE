"""Migration environment, using the same ALLSAFE_ settings as the API."""

from logging.config import fileConfig

from alembic import context
from allsafe_api.config import Settings
from allsafe_api.database import build_engine, prepare_database_directory
from allsafe_api.models import Base
from allsafe_api.phishcatch import models as phishcatch_models  # noqa: F401
from allsafe_api.wazuh import models as wazuh_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    prepare_database_directory(settings.database_url)
    connectable = build_engine(settings.database_url)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
