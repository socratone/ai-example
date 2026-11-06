"""로컬 터미널과 Modal GPU의 계산 에이전트를 연결합니다."""

import modal

MODEL_ID = "Qwen/Qwen3-1.7B"
CACHE_DIR = "/model-cache"
PORT = 8000

# Volume은 컨테이너가 종료된 뒤에도 다운로드한 모델 파일을 보관합니다.
app = modal.App("ai-example-langgraph-calculator")
cache = modal.Volume.from_name("ai-example-langgraph-calculator-cache", create_if_missing=True)
# 로컬에는 Modal과 LangGraph만 필요합니다. vLLM과 모델 호출 라이브러리는 원격 이미지에 설치합니다.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("vllm>=0.8.5,<1", "langgraph>=1,<2", "langchain-openai>=1,<2")
    .env({"HF_HOME": CACHE_DIR})
    .add_local_python_source("langgraph_calculator")
)


# 이 클래스의 메서드는 .remote(...)로 호출할 때 Modal GPU 컨테이너에서 실행됩니다.
@app.cls(image=image, gpu="any", volumes={CACHE_DIR: cache}, timeout=600)
class CalculatorAgent:
    @modal.enter()
    def start(self) -> None:
        """컨테이너가 시작될 때 모델 서버와 LangGraph를 한 번 준비합니다."""
        import subprocess
        import time
        import urllib.error
        import urllib.request

        from langchain_openai import ChatOpenAI
        from langgraph_calculator.agent import build_graph

        # vLLM은 같은 컨테이너 안에서만 접근할 수 있는 HTTP 서버로 모델을 실행합니다.
        # Hermes 파서는 모델의 도구 호출 출력을 구조화된 tool_calls로 바꿉니다.
        self.server = subprocess.Popen(
            [
                "vllm", "serve", MODEL_ID,
                "--host", "127.0.0.1", "--port", str(PORT),
                "--dtype", "float16", "--max-model-len", "4096",
                "--enforce-eager",
                "--enable-auto-tool-choice", "--tool-call-parser", "hermes",
            ]
        )
        # 모델 다운로드와 로드가 끝나기 전에는 서버에 요청할 수 없으므로 준비 상태를 기다립니다.
        health_url = f"http://127.0.0.1:{PORT}/health"
        deadline = time.monotonic() + 480
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError("vLLM 서버가 시작 중 종료되었습니다.")
            try:
                with urllib.request.urlopen(health_url, timeout=2):
                    break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        else:
            raise TimeoutError("vLLM 서버 시작 시간이 초과되었습니다.")

        # 모델 파일을 다음 컨테이너에서도 재사용할 수 있게 Volume에 반영합니다.
        cache.commit()
        # ChatOpenAI는 외부 OpenAI API가 아니라 위에서 시작한 vLLM 서버를 호출합니다.
        # vLLM은 API 키를 검사하지 않지만 클라이언트 생성에 값이 필요해 EMPTY를 넣습니다.
        model = ChatOpenAI(
            model=MODEL_ID,
            base_url=f"http://127.0.0.1:{PORT}/v1",
            api_key="EMPTY",
            use_responses_api=False,
            temperature=0.7,
            max_tokens=256,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        self.graph = build_graph(model)

    @modal.exit()
    def stop(self) -> None:
        """GPU 컨테이너가 끝날 때 함께 실행한 모델 서버를 종료합니다."""
        self.server.terminate()
        try:
            self.server.wait(timeout=10)
        except Exception:
            self.server.kill()
            self.server.wait()

    @modal.method()
    def generate(self, question: str) -> str:
        """질문 하나를 그래프에 넣고 최종 답변만 반환합니다."""
        from langgraph_calculator.agent import ask

        return ask(self.graph, question)


@app.local_entrypoint()
def main() -> None:
    """로컬 터미널의 입력을 Modal 원격 메서드에 전달합니다."""
    from langgraph_calculator.cli import run_chat

    agent = CalculatorAgent()
    # 질문을 입력할 때마다 새 그래프 실행이 시작되므로 이전 대화는 전달되지 않습니다.
    run_chat(lambda question: agent.generate.remote(question))
