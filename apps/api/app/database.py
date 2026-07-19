from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            echo=False,
        )
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if self.engine.url.drivername.startswith("sqlite"):
                columns = {
                    row[1]
                    for row in (
                        await connection.execute(text("PRAGMA table_info(processing_jobs)"))
                    ).all()
                }
                additions = {
                    "processing_stage": (
                        "ALTER TABLE processing_jobs ADD COLUMN processing_stage "
                        "VARCHAR(32) NOT NULL DEFAULT 'queued'"
                    ),
                    "stage_started_at": (
                        "ALTER TABLE processing_jobs ADD COLUMN stage_started_at DATETIME"
                    ),
                    "heartbeat_at": "ALTER TABLE processing_jobs ADD COLUMN heartbeat_at DATETIME",
                }
                for name, statement in additions.items():
                    if name not in columns:
                        await connection.execute(text(statement))

                session_columns = {
                    row[1]
                    for row in (
                        await connection.execute(text("PRAGMA table_info(practice_sessions)"))
                    ).all()
                }
                if "interaction_events" not in session_columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE practice_sessions ADD COLUMN interaction_events "
                            "JSON NOT NULL DEFAULT '[]'"
                        )
                    )

                evaluation_columns = {
                    row[1]
                    for row in (
                        await connection.execute(text("PRAGMA table_info(evaluations)"))
                    ).all()
                }
                if "interactive_communication_result" not in evaluation_columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE evaluations ADD COLUMN "
                            "interactive_communication_result JSON"
                        )
                    )
        if self.engine.url.drivername.startswith("sqlite"):
            await self._migrate_sqlite_practice_tasks()

    async def _migrate_sqlite_practice_tasks(self) -> None:
        """Rebuild the task table when an older Part-2-only database is mounted."""
        async with self.engine.connect() as connection:
            table_sql = (
                await connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name='practice_tasks'"
                    )
                )
            ).scalar_one_or_none()
            columns = {
                row[1]
                for row in (
                    await connection.execute(text("PRAGMA table_info(practice_tasks)"))
                ).all()
            }
            task_additions = {
                "questions": (
                    "ALTER TABLE practice_tasks ADD COLUMN questions JSON NOT NULL DEFAULT '[]'"
                ),
                "setup": ("ALTER TABLE practice_tasks ADD COLUMN setup TEXT NOT NULL DEFAULT ''"),
                "decision_question": (
                    "ALTER TABLE practice_tasks ADD COLUMN decision_question "
                    "TEXT NOT NULL DEFAULT ''"
                ),
            }
            for name, statement in task_additions.items():
                if name not in columns:
                    await connection.execute(text(statement))
            if any(name not in columns for name in task_additions):
                await connection.commit()
            needs_rebuild = table_sql is not None and "part = 2" in table_sql
            if not needs_rebuild:
                return

            await connection.commit()
            await connection.execute(text("PRAGMA foreign_keys=OFF"))
            await connection.execute(text("PRAGMA legacy_alter_table=ON"))
            await connection.commit()
            try:
                async with connection.begin():
                    await connection.execute(
                        text("ALTER TABLE practice_tasks RENAME TO practice_tasks_legacy")
                    )
                    task_table = Base.metadata.tables["practice_tasks"]
                    await connection.run_sync(
                        lambda sync_connection: task_table.create(sync_connection, checkfirst=False)
                    )
                    migration_sql = """
                            INSERT INTO practice_tasks (
                                id, part, version, status, examiner_instruction,
                                examiner_audio_path, setup, question, questions,
                                decision_question, image_one_path,
                                image_two_path, photo_one_keywords, photo_two_keywords,
                                license_information, content_notice, teacher_approved_at,
                                created_at
                            )
                            SELECT
                                id, part, version, status, examiner_instruction,
                                examiner_audio_path, setup, question, questions,
                                decision_question, image_one_path,
                                image_two_path, photo_one_keywords, photo_two_keywords,
                                license_information, content_notice, teacher_approved_at,
                                created_at
                            FROM practice_tasks_legacy
                            """
                    await connection.execute(text(migration_sql))
                    await connection.execute(text("DROP TABLE practice_tasks_legacy"))
            finally:
                await connection.execute(text("PRAGMA legacy_alter_table=OFF"))
                await connection.execute(text("PRAGMA foreign_keys=ON"))
                await connection.commit()

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as db_session:
            yield db_session
