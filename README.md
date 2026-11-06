# ai-example

uv 워크스페이스 기반 모노레포입니다. `modal-chat`은 Modal GPU의 Qwen 모델과 대화하는 터미널 앱입니다. `langgraph-calculator`는 LangGraph가 사칙연산 도구를 호출할 수 있는 별도 터미널 앱입니다. 두 앱 모두 질문마다 독립적으로 처리하며 대화 기록은 저장하지 않습니다.

## 준비

Python 3.12와 uv가 필요합니다. Modal 계정과 GPU 사용을 위한 결제 수단도 등록해야 합니다.

```sh
uv sync --package modal-chat
uv run --package modal-chat modal setup
```

`modal setup`은 처음 한 번만 실행하면 됩니다.

## 실행

```sh
uv run --package modal-chat modal run -q -m modal_chat.app
```

계산 도구 앱은 다음 명령으로 실행합니다. 자세한 설명은 [langgraph-calculator README](apps/langgraph-calculator/README.md)를 참고하세요.

```sh
uv sync --package langgraph-calculator
uv run --package langgraph-calculator modal run -q -m langgraph_calculator.app
```

`-q`는 Modal의 진행 표시가 터미널 입력 프롬프트와 겹치지 않도록 합니다. `질문> ` 프롬프트에 메시지를 입력합니다. `/exit`으로 종료할 수 있습니다. 첫 실행에서는 원격 이미지 생성과 모델 다운로드 때문에 시간이 걸릴 수 있습니다. 모델 파일은 Modal Volume에 캐시됩니다. 응답은 생성 완료 후 한 번에 표시됩니다.

## 테스트

```sh
uv run --package modal-chat python -m unittest discover -s apps/modal-chat/tests
uv run --package langgraph-calculator python -m unittest discover -s apps/langgraph-calculator/tests
```

이 테스트는 Modal 호출 없이 터미널 입력과 오류 처리를 확인합니다.
