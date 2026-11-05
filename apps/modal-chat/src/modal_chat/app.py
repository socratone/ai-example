"""터미널 질문을 Modal GPU의 LangChain 모델로 전달합니다."""

import modal

MODEL_ID = "Qwen/Qwen3-1.7B"
CACHE_DIR = "/model-cache"

# 앱 이름, 모델 파일을 보관할 저장소, 원격 컨테이너 환경을 정의합니다.
app = modal.App("ai-example-modal-chat")
cache = modal.Volume.from_name("ai-example-modal-chat-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("torch", "transformers>=5,<6", "langchain-huggingface==1.2.3")
    .env({"HF_HOME": CACHE_DIR})
)


# 이 클래스의 메서드는 Modal의 L4 GPU 컨테이너에서 실행됩니다.
@app.cls(image=image, gpu="L4", volumes={CACHE_DIR: cache}, timeout=600)
class ChatModel:
    # 새 컨테이너가 시작될 때 한 번 실행되므로 모델을 매 질문마다 로드하지 않습니다.
    @modal.enter()
    def load(self) -> None:
        """새 GPU 컨테이너에서 모델을 한 번 로드합니다."""
        from langchain_huggingface import HuggingFacePipeline

        # LangChain이 Hugging Face 모델 로드와 텍스트 생성을 감쌉니다.
        self.llm = HuggingFacePipeline.from_model_id(
            model_id=MODEL_ID,
            task="text-generation",
            device=0,
            model_kwargs={"dtype": "auto"},
            pipeline_kwargs={
                "max_new_tokens": 256,
                "do_sample": True,
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 20,
            },
        )
        # 다운로드한 모델 파일을 다음 컨테이너에서도 쓸 수 있게 저장합니다.
        cache.commit()

    # .remote(prompt)로 호출하면 이 메서드가 내 컴퓨터 대신 Modal에서 실행됩니다.
    @modal.method()
    def generate(self, prompt: str) -> str:
        """질문을 Qwen 채팅 형식으로 만들고 LangChain으로 답변을 받습니다."""
        # Qwen의 채팅 형식을 적용하고 긴 추론 출력(thinking)은 끕니다.
        chat_prompt = self.llm.pipeline.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        # skip_prompt=True는 결과에서 입력 질문 부분을 제외합니다.
        return self.llm.invoke(chat_prompt, skip_prompt=True).strip()


# 이 함수는 Modal이 아니라 내 컴퓨터에서 실행됩니다.
@app.local_entrypoint()
def main() -> None:
    """로컬 터미널의 질문을 Modal 원격 메서드에 연결합니다."""
    from modal_chat.cli import run_chat

    model = ChatModel()
    # lambda는 터미널의 질문을 generate.remote(...)로 전달하는 짧은 함수입니다.
    run_chat(lambda prompt: model.generate.remote(prompt))
