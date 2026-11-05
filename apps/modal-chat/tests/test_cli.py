"""Tests for local chat interaction without a Modal account or GPU."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from modal_chat.cli import run_chat


class ChatCliTests(unittest.TestCase):
    def test_independent_questions_and_exit(self) -> None:
        prompts = []

        def ask(prompt: str) -> str:
            prompts.append(prompt)
            return f"답변: {prompt}"

        output = io.StringIO()
        with patch("builtins.input", side_effect=["  ", "  첫 질문  ", "둘째 질문", "/exit"]):
            with redirect_stdout(output):
                run_chat(ask)

        self.assertEqual(prompts, ["첫 질문", "둘째 질문"])
        self.assertIn("AI> 답변: 첫 질문", output.getvalue())
        self.assertIn("AI> 답변: 둘째 질문", output.getvalue())

    def test_remote_error_does_not_end_session(self) -> None:
        calls = 0

        def ask(prompt: str) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("일시적인 오류")
            return "복구됨"

        output = io.StringIO()
        errors = io.StringIO()
        with patch("builtins.input", side_effect=["첫 질문", "다시", "/exit"]):
            with redirect_stdout(output), redirect_stderr(errors):
                run_chat(ask)

        self.assertEqual(calls, 2)
        self.assertIn("요청 실패: 일시적인 오류", errors.getvalue())
        self.assertIn("AI> 복구됨", output.getvalue())

    def test_end_of_input_exits(self) -> None:
        with patch("builtins.input", side_effect=EOFError):
            with redirect_stdout(io.StringIO()):
                run_chat(lambda _: self.fail("should not send a question"))


if __name__ == "__main__":
    unittest.main()
