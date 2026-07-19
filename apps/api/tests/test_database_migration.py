from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from sqlalchemy import select

from app.config import Settings
from app.database import Database
from app.models import PracticeTask


def test_part2_only_sqlite_database_is_migrated_without_data_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE practice_tasks (
            id VARCHAR(36) PRIMARY KEY,
            part INTEGER NOT NULL,
            version VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL,
            examiner_instruction TEXT NOT NULL,
            examiner_audio_path VARCHAR(255) NOT NULL,
            question TEXT NOT NULL,
            image_one_path VARCHAR(255) NOT NULL,
            image_two_path VARCHAR(255) NOT NULL,
            photo_one_keywords JSON NOT NULL,
            photo_two_keywords JSON NOT NULL,
            license_information TEXT NOT NULL,
            content_notice TEXT NOT NULL,
            teacher_approved_at DATETIME,
            created_at DATETIME NOT NULL,
            CONSTRAINT practice_tasks_part_two_only CHECK (part = 2),
            CONSTRAINT practice_tasks_status CHECK (
                status in ('draft','published','retired')
            )
        );
        INSERT INTO practice_tasks VALUES (
            'legacy-task', 2, 'v1', 'published', 'instruction', '/audio.mp3',
            'question', '/one.jpg', '/two.jpg', '[]', '[]', 'license', 'notice',
            NULL, '2026-07-16 10:00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            environment="test",
            database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
            session_token_pepper=(  # noqa: S106
                "test-session-pepper-with-more-than-32-characters"
            ),
            upload_signing_secret=(  # noqa: S106
                "test-upload-signing-secret-with-32-characters"
            ),
            teacher_validation_token="teacher-test-token",  # noqa: S106
        )
        database = Database(settings)
        await database.create_schema()
        async with database.sessions() as session:
            legacy = await session.scalar(
                select(PracticeTask).where(PracticeTask.id == "legacy-task")
            )
            assert legacy is not None
            assert legacy.part == 2
            assert legacy.questions == []

            session.add(
                PracticeTask(
                    id="part1-task",
                    part=1,
                    version="v1",
                    status="published",
                    examiner_instruction="instruction",
                    examiner_audio_path="/audio.mp3",
                    question="question",
                    questions=["question one", "question two", "question three"],
                    image_one_path="",
                    image_two_path="",
                    photo_one_keywords=[],
                    photo_two_keywords=[],
                    license_information="license",
                    content_notice="notice",
                )
            )
            await session.commit()
        await database.dispose()

    asyncio.run(scenario())

    connection = sqlite3.connect(database_path)
    part_one = connection.execute(
        "SELECT part, questions FROM practice_tasks WHERE id = 'part1-task'"
    ).fetchone()
    foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
    connection.close()

    assert part_one == (1, '["question one", "question two", "question three"]')
    assert foreign_key_issues == []
