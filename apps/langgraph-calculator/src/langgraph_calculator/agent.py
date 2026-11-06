"""모델이 필요할 때 계산 도구를 호출하는 LangGraph를 정의합니다."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from langgraph_calculator.calculator import evaluate


@tool
def calculate(expression: str) -> str:
    """괄호와 소수를 포함한 사칙연산 수식을 계산합니다."""
    # 오류도 도구 결과로 돌려주면 모델이 사용자에게 원인을 설명할 수 있습니다.
    try:
        return evaluate(expression)
    except ValueError as exc:
        return f"계산 오류: {exc}"


SYSTEM_PROMPT = (
    "한국어로 간결하게 답하세요. 계산이 필요한 질문에는 반드시 calculate 도구를 "
    "사용하고, 도구가 반환한 값을 바꾸지 마세요. 계산 오류가 나면 그 이유를 설명하세요."
)


def build_graph(model):
    """모델 → 도구 → 모델 순서로 이어지는 그래프를 만듭니다."""
    # 도구의 이름과 입력 형식을 모델에 알려 주어 tool_calls를 생성할 수 있게 합니다.
    model_with_tools = model.bind_tools([calculate])

    def call_model(state: MessagesState):
        # messages에는 질문, 모델의 도구 호출, 도구 결과가 순서대로 쌓입니다.
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # 모델이 도구를 요청하면 tools로, 요청하지 않으면 END로 이동합니다.
    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode([calculate]))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
    # 계산 결과를 본 모델이 자연어 최종 답변을 만들도록 다시 모델로 보냅니다.
    graph.add_edge("tools", "model")
    return graph.compile()


def ask(graph, question: str) -> str:
    """질문 하나를 독립적으로 실행하고 마지막 모델 답변을 반환합니다."""
    # 매번 새 메시지 목록을 주고 체크포인터를 쓰지 않아 대화 기록이 유지되지 않습니다.
    result = graph.invoke(
        {"messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(question)]},
        config={"recursion_limit": 8},  # 모델이 도구를 무한히 반복 호출하지 않도록 제한합니다.
    )
    answer = result["messages"][-1]
    if not isinstance(answer, AIMessage) or not isinstance(answer.content, str):
        raise RuntimeError("모델이 텍스트 답변을 반환하지 않았습니다.")
    return answer.content.strip()
