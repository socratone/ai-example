"""Terminal behavior without a Modal account."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from langgraph_calculator.cli import run_chat


class CliTests(unittest.TestCase):
    def test_questions_and_exit(self) -> None:
        prompts = []
        output = io.StringIO()
        with patch("builtins.input", side_effect=[" ", " 12.5 * (8 - 3) ", "/exit"]):
            with redirect_stdout(output):
                run_chat(lambda prompt: prompts.append(prompt) or "62.5")
        self.assertEqual(prompts, ["12.5 * (8 - 3)"])
        self.assertIn("AI> 62.5", output.getvalue())

    def test_error_then_recovery(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
