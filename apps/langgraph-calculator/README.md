# langgraph-calculator

터미널에서 질문하면 Modal GPU의 `Qwen/Qwen3-1.7B` 모델이 답합니다. 계산이 필요할 때 LangGraph가 `calculate` 도구를 실행한 뒤 그 결과를 모델에 전달합니다. 괄호, 소수, 사칙연산을 지원하며 각 질문은 독립적입니다.

## 준비와 실행

저장소 루트에서 실행합니다. Python 3.12, uv, Modal 계정과 GPU 결제 수단이 필요합니다. 외부 AI API 키는 사용하지 않습니다.

```sh
uv sync --package langgraph-calculator
uv run --package langgraph-calculator modal setup  # Modal 인증을 아직 하지 않았다면 한 번만
uv run --package langgraph-calculator modal run -q -m langgraph_calculator.app
```

```text
질문을 입력하세요. 종료하려면 /exit를 입력하세요.
질문> 12.5 * (8 - 3)을 계산해 줘
AI> 62.5입니다.
질문> /exit
```

답변 표현은 실행마다 다를 수 있습니다. 첫 실행은 이미지 생성과 모델 다운로드로 오래 걸릴 수 있으며, GPU 사용에는 Modal 요금이 발생합니다. 모델 파일은 Modal Volume에 캐시됩니다.

## 동작

로컬 CLI가 질문을 `CalculatorAgent.generate.remote()`로 보냅니다. Modal 컨테이너는 내부 vLLM 서버에서 모델을 실행합니다. LangGraph는 모델 응답에 도구 호출이 있으면 계산 도구를 실행하고 결과를 모델에 다시 보냅니다. 계산 도구는 Python 코드를 실행하지 않고 허용된 수식만 해석합니다. 이전 질문은 다음 질문에 전달하지 않습니다.

## 로컬 테스트

Modal 계정이나 GPU 없이 계산기, LangGraph 경로, 터미널 오류 처리를 확인합니다.

```sh
uv run --package langgraph-calculator python -m unittest discover -s apps/langgraph-calculator/tests
```
