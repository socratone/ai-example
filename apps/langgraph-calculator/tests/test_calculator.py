"""Calculator and graph tests that do not need Modal or a GPU."""

import unittest

from langchain_core.messages import AIMessage, ToolMessage

from langgraph_calculator.agent import ask, build_graph, calculate
from langgraph_calculator.calculator import evaluate


class CalculatorTests(unittest.TestCase):
    def test_arithmetic(self) -> None:
        self.assertEqual(evaluate("12.5 * (8 - 3)"), "62.5")
        self.assertEqual(evaluate("0.1 + 0.2"), "0.3")
        self.assertEqual(evaluate("-8 / 4 + +3"), "1")
        self.assertEqual(evaluate("2 + 3 * 4"), "14")

    def test_rejects_unsupported_expressions(self) -> None:
        for expression in ("2 ** 3", "abs(-1)", "__import__('os')", "True", "1 // 2"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate(expression)

    def test_invalid_and_zero_division(self) -> None:
        with self.assertRaisesRegex(ValueError, "0으로 나눌"):
            evaluate("1 / 0")
        with self.assertRaises(ValueError):
            evaluate("1 +")
        self.assertIn("계산 오류", calculate.invoke({"expression": "1 / 0"}))


class FakeModel:
    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            result = next(message.content for message in messages if isinstance(message, ToolMessage))
            return AIMessage(content=f"결과는 {result}입니다.")
        if "계산" in messages[-1].content:
            return AIMessage(
                content="",
                tool_calls=[{"name": "calculate", "args": {"expression": "12.5 * (8 - 3)"}, "id": "call-1"}],
            )
        return AIMessage(content="안녕하세요!")


class AgentTests(unittest.TestCase):
    def test_tool_route_and_plain_answer(self) -> None:
        model = FakeModel()
        graph = build_graph(model)
        self.assertEqual(ask(graph, "계산해 줘"), "결과는 62.5입니다.")
        self.assertEqual(ask(graph, "안녕"), "안녕하세요!")
        self.assertEqual(len(model.tools), 1)


if __name__ == "__main__":
    unittest.main()
