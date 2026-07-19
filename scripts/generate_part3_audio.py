from __future__ import annotations

import asyncio
import ast
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
VOICE = "en-GB-SoniaNeural"
OUTPUT = ROOT / "apps" / "web" / "public" / "assets" / "temporary-part3"


def part3_content() -> list[dict[str, object]]:
    source = ROOT / "apps" / "api" / "app" / "sample_data.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PART_3_CONTENT"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("PART_3_CONTENT was not found")


async def save(text: str, filename: str) -> None:
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(str(OUTPUT / filename))


async def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        save("Thank you. That's the end of Part 3.", "examiner-closing-sonia.mp3")
    ]
    for practice, content in enumerate(part3_content(), start=1):
        question = str(content["question"])
        decision = str(content["decision_question"])
        jobs.extend(
            [
                save(
                    "Now, I'd like you to talk about something together for about two "
                    f"minutes. {content['setup']} Talk to each other about "
                    f"{question[0].lower() + question[1:]}",
                    f"examiner-p3-{practice:03d}-intro-sonia.mp3",
                ),
                save(
                    "Thank you. Now you have about a minute to decide "
                    f"{decision[0].lower() + decision[1:]}",
                    f"examiner-p3-{practice:03d}-decision-sonia.mp3",
                ),
            ]
        )
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
