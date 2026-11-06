"""로컬 터미널에서 질문을 읽고 Modal이 반환한 답변을 출력합니다."""

import sys
from collections.abc import Callable


def run_chat(ask: Callable[[str], str]) -> None:
    """종료 명령을 받을 때까지 질문을 원격 호출 함수에 전달합니다."""
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

        # 한 번의 원격 호출이 실패해도 입력 루프는 계속 실행합니다.
        try:
            answer = ask(prompt)
        except Exception as exc:
            print(f"요청 실패: {exc}", file=sys.stderr)
            continue
        print(f"AI> {answer}")
