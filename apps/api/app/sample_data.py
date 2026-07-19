from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PracticeTask

SAMPLE_TASK_ID = "99999999-9999-4999-8999-999999999999"


def _part1_task(task_id: str, practice_number: int, questions: list[str]) -> dict[str, Any]:
    return {
        "id": task_id,
        "part": 1,
        "version": "open-original-part1-v1",
        "status": "published",
        "examiner_instruction": (
            "Good morning. My name is Sonia. I'd like to ask you some questions about yourself."
        ),
        "examiner_audio_path": "/assets/temporary-part1/examiner-intro-sonia.mp3",
        "question": " / ".join(questions),
        "questions": questions,
        "image_one_path": "",
        "image_two_path": "",
        "photo_one_keywords": [],
        "photo_two_keywords": [],
        "license_information": "Original interview task distributed with the open edition.",
        "content_notice": (
            "Tarea original inspirada en el formato de B2 First Speaking Part 1. "
            "No es material ni evaluación oficial de Cambridge."
        ),
    }


def _part2_task(
    *,
    task_id: str,
    practice_number: int,
    scene: str,
    question: str,
    image_one: str,
    image_two: str,
    photo_one_keywords: list[str],
    photo_two_keywords: list[str],
) -> dict[str, Any]:
    return {
        "id": task_id,
        "part": 2,
        "version": "open-original-part2-v1",
        "status": "published",
        "examiner_instruction": (
            f"Now look at the two photographs. They show {scene.lower()} "
            f"Please compare the photographs and say {question[0].lower() + question[1:]} "
            "You have one minute."
        ),
        "examiner_audio_path": (
            f"/assets/temporary-part2/examiner-p2-{practice_number:03d}-sonia.mp3"
        ),
        "question": question,
        "questions": [],
        "image_one_path": image_one,
        "image_two_path": image_two,
        "photo_one_keywords": ["first photograph", "first picture", *photo_one_keywords],
        "photo_two_keywords": ["second photograph", "second picture", *photo_two_keywords],
        "license_information": (
            "Original task with photographs distributed under the Unsplash License. "
            "Sources and hashes are recorded in the asset manifest."
        ),
        "content_notice": (
            "Tarea original con fotografías de licencia trazable. "
            "No es material ni evaluación oficial de Cambridge."
        ),
    }


def _part3_task(
    task_id: str,
    practice_number: int,
    content: dict[str, object],
) -> dict[str, Any]:
    question = str(content["question"])
    setup = str(content["setup"])
    prompts = [str(prompt) for prompt in content["prompts"]]  # type: ignore[union-attr]
    return {
        "id": task_id,
        "part": 3,
        "version": "open-original-part3-v1",
        "status": "published",
        "examiner_instruction": (
            "Now, I'd like you to talk about something together for about two minutes. "
            f"{setup} Talk to each other about {question[0].lower() + question[1:]}"
        ),
        "examiner_audio_path": (
            f"/assets/temporary-part3/examiner-p3-{practice_number:03d}-intro-sonia.mp3"
        ),
        "setup": setup,
        "question": question,
        "questions": prompts,
        "decision_question": str(content["decision_question"]),
        "image_one_path": "",
        "image_two_path": "",
        "photo_one_keywords": prompts,
        "photo_two_keywords": [],
        "license_information": "Original collaborative task distributed with the open edition.",
        "content_notice": (
            "Tarea original inspirada en el formato de B2 First Speaking Part 3. "
            "No es material ni evaluación oficial de Cambridge."
        ),
    }


PART_1_TASKS = [
    _part1_task(
        "d9999999-9999-4999-8999-999999999999",
        9,
        [
            "Do you work or are you a student? What do you like most about it?",
            "What do you usually do when you finish work or classes? Why?",
            "Would you like to learn something new this year? What would it be?",
        ],
    ),
    _part1_task(
        "daaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        10,
        [
            "Tell us about the place where you live. What do you like about it?",
            "Do you prefer living in a city or in a small town? Why?",
            "What would you change about your neighbourhood if you could? Why?",
        ],
    ),
    _part1_task(
        "dbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        11,
        [
            "What kind of food do you enjoy eating most? Why?",
            "Do you prefer eating at home or in restaurants? Why?",
            "Tell us about a meal you really enjoyed recently.",
        ],
    ),
    _part1_task(
        "dccccccc-cccc-4ccc-8ccc-cccccccccccc",
        12,
        [
            "How do you usually spend your free time at the weekend?",
            "Do you prefer holidays in your own country or abroad? Why?",
            "Tell us about a place you would like to visit in the future.",
        ],
    ),
]
PART_1_TASK_IDS = [str(task["id"]) for task in PART_1_TASKS]


PART_2_TASKS = [
    _part2_task(
        task_id=SAMPLE_TASK_ID,
        practice_number=9,
        scene="people learning practical skills in different situations.",
        question="What might the people find useful about learning in these ways?",
        image_one="/practice-assets/original/academy-part2/p2-009-photo-a.jpg",
        image_two="/practice-assets/original/academy-part2/p2-009-photo-b.jpg",
        photo_one_keywords=["cooking", "kitchen", "food", "teacher", "together"],
        photo_two_keywords=["students", "laptops", "group", "table", "together"],
    ),
    _part2_task(
        task_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        practice_number=10,
        scene="people exercising in different situations.",
        question="Why might the people have chosen to exercise in these ways?",
        image_one="/practice-assets/original/academy-part2/p2-010-photo-a.jpg",
        image_two="/practice-assets/original/academy-part2/p2-010-photo-b.jpg",
        photo_one_keywords=["gym", "weights", "indoor", "training", "equipment"],
        photo_two_keywords=["runners", "running", "outdoor", "group", "track"],
    ),
    _part2_task(
        task_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        practice_number=11,
        scene="people enjoying different social occasions.",
        question="What might the people enjoy about these social occasions?",
        image_one="/practice-assets/original/academy-part2/p2-011-photo-a.jpg",
        image_two="/practice-assets/original/academy-part2/p2-011-photo-b.jpg",
        photo_one_keywords=["concert", "crowd", "music", "event", "excited"],
        photo_two_keywords=["meal", "table", "friends", "food", "conversation"],
    ),
    _part2_task(
        task_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        practice_number=12,
        scene="people working in different places.",
        question="What might be difficult about working in these places?",
        image_one="/practice-assets/original/academy-part2/p2-012-photo-a.jpg",
        image_two="/practice-assets/original/academy-part2/p2-012-photo-b.jpg",
        photo_one_keywords=["office", "colleagues", "meeting", "conversation", "shared"],
        photo_two_keywords=["home", "laptop", "remote", "alone", "computer"],
    ),
]


PART_3_CONTENT: list[tuple[str, int, dict[str, object]]] = [
    (
        "e5555555-5555-4555-8555-555555555555",
        5,
        {
            "setup": "A company wants its employees to feel happier at work.",
            "question": "How would these ideas help employees feel happier at work?",
            "prompts": [
                "flexible working hours",
                "a free gym in the office",
                "more team activities",
                "longer holidays",
                "a quiet room for breaks",
            ],
            "decision_question": "Which idea would make the biggest difference?",
        },
    ),
    (
        "e6666666-6666-4666-8666-666666666666",
        6,
        {
            "setup": "These are ways people can protect the environment in their daily lives.",
            "question": "How useful are these ways of protecting the environment?",
            "prompts": [
                "using public transport",
                "recycling at home",
                "buying second-hand clothes",
                "eating less meat",
                "saving water and electricity",
            ],
            "decision_question": "Which two are the easiest for most people to do every day?",
        },
    ),
    (
        "e7777777-7777-4777-8777-777777777777",
        7,
        {
            "setup": "A family is deciding how to spend a free Saturday together.",
            "question": "Why might the family enjoy spending the day in these ways?",
            "prompts": [
                "visiting a museum",
                "having a picnic in the countryside",
                "watching films at home",
                "going shopping in town",
                "doing sport together",
            ],
            "decision_question": "Which plan would be best for the whole family?",
        },
    ),
    (
        "e8888888-8888-4888-8888-888888888888",
        8,
        {
            "setup": "These are things people often think about when choosing a job.",
            "question": "How important are these things when choosing a job?",
            "prompts": [
                "a good salary",
                "friendly colleagues",
                "working near home",
                "opportunities to learn",
                "long holidays",
            ],
            "decision_question": ("Which two matter most for someone starting their first job?"),
        },
    ),
]

PART_3_TASKS = [
    _part3_task(task_id, practice_number, content)
    for task_id, practice_number, content in PART_3_CONTENT
]
PART_3_TASK_IDS = [str(task["id"]) for task in PART_3_TASKS]

PART2_FOLLOW_UP_QUESTIONS = {
    SAMPLE_TASK_ID: "Which way of learning would you prefer? Why?",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": (
        "Do you prefer exercising alone or with other people? Why?"
    ),
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": ("Which occasion would you prefer to attend? Why?"),
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc": "Where would you prefer to work? Why?",
}


async def seed_sample_task(db: AsyncSession) -> None:
    for payload in [*PART_1_TASKS, *PART_2_TASKS, *PART_3_TASKS]:
        existing = await db.scalar(select(PracticeTask).where(PracticeTask.id == payload["id"]))
        if existing is None:
            db.add(PracticeTask(**payload))
            continue
        for field, value in payload.items():
            if field != "id":
                setattr(existing, field, value)
    await db.commit()
