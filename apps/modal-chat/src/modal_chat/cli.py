"""Local terminal interaction for independent questions."""

import sys
from collections.abc import Callable


def run_chat(ask: Callable[[str], str]) -> None:
    """Read questions and display responses until the user exits."""
    print("질문을 입력하세요. 종료하려면 /exit를 입력하세요.")
    while True:
        try:
            prompt = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if prompt == "/exit":
            return
        if not prompt:
            continue

        try:
            answer = ask(prompt)
        except Exception as exc:
            print(f"요청 실패: {exc}", file=sys.stderr)
            continue

        print(f"AI> {answer}")
