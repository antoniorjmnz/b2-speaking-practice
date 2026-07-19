from __future__ import annotations

import asyncio
import ast
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]

VOICE = "en-GB-SoniaNeural"
OUTPUT = ROOT / "apps" / "web" / "public" / "assets" / "temporary-part1"


def question_sets() -> list[list[str]]:
    source_path = ROOT / "apps" / "api" / "app" / "sample_data.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PART_1_QUESTION_SETS"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("PART_1_QUESTION_SETS was not found")


async def save(text: str, filename: str) -> None:
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(str(OUTPUT / filename))


async def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        save(
            "Good morning. My name is Sonia. I'd like to ask you some questions about yourself.",
            "examiner-intro-sonia.mp3",
        ),
        save("Thank you. That's the end of Part 1.", "examiner-closing-sonia.mp3"),
    ]
    for practice, questions in enumerate(question_sets(), start=1):
        for question, text in enumerate(questions, start=1):
            jobs.append(
                save(
                    text,
                    f"examiner-p1-{practice:03d}-q{question}-sonia.mp3",
                )
            )
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
