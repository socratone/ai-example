"""터미널에서 받은 질문을 Modal GPU의 AI 모델에 보내는 앱."""

import modal

# 사용할 AI 모델과 원격 컨테이너 안에서 모델 파일을 저장할 경로입니다.
MODEL_ID = "Qwen/Qwen3-1.7B"
CACHE_DIR = "/model-cache"

# Modal 앱의 이름과, 다운로드한 모델 파일을 보관할 저장소(Volume)를 만듭니다.
# 이 코드는 설정을 정의하며, 여기서 바로 GPU가 실행되는 것은 아닙니다.
app = modal.App("ai-example-modal-chat")
cache = modal.Volume.from_name("ai-example-modal-chat-cache", create_if_missing=True)

# 원격 GPU 컨테이너의 실행 환경입니다. torch와 transformers는 내 컴퓨터가
# 아니라 이 컨테이너에 설치됩니다. HF_HOME은 모델 캐시 위치를 지정합니다.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("torch", "transformers>=4.51,<5", "huggingface_hub")
    .env({"HF_HOME": CACHE_DIR})
)


# @app.cls는 아래 클래스를 Modal의 L4 GPU에서 실행하도록 등록합니다.
# volumes는 위에서 만든 저장소를 컨테이너의 /model-cache에 연결합니다.
@app.cls(image=image, gpu="L4", volumes={CACHE_DIR: cache}, timeout=600)
class ChatModel:
    # 새 원격 컨테이너가 시작될 때 한 번 실행됩니다. 같은 컨테이너에서 여러
    # 질문을 처리하면 이미 로드한 모델을 재사용할 수 있습니다.
    @modal.enter()
    def load(self) -> None:
        """모델과 토크나이저를 준비합니다. None은 반환값이 없다는 뜻입니다."""
        # 원격 컨테이너에 설치한 패키지이므로 원격에서 실행되는 함수 안에서 가져옵니다.
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # 토크나이저는 글을 숫자 토큰으로 바꾸고, 모델은 답변 토큰을 생성합니다.
        # self에 저장하면 같은 ChatModel 객체의 generate()에서도 사용할 수 있습니다.
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto").to(
            "cuda"
        )
        # 학습이 아닌 답변 생성 모드로 설정하고, 다운로드한 파일을 Volume에 저장합니다.
        self.model.eval()
        cache.commit()

    # @modal.method가 붙은 함수는 .remote(...)로 원격 호출할 수 있습니다.
    @modal.method()
    def generate(self, prompt: str) -> str:
        """문자열 질문(prompt)을 받아 문자열 답변을 돌려줍니다."""
        import torch

        # 각 요청에는 현재 질문만 넣습니다. 이전 질문이나 답변은 전달하지 않습니다.
        # 채팅 형식으로 변환한 토큰을 모델이 있는 GPU로 옮깁니다.
        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_tensors="pt",
        ).to("cuda")
        # 답변을 만들 때는 학습용 기울기를 계산할 필요가 없습니다.
        with torch.inference_mode():
            output = self.model.generate(
                inputs,
                # 답변 길이를 최대 256개의 새 토큰으로 제한합니다.
                max_new_tokens=256,
                do_sample=True,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        # output에는 입력 질문 토큰도 포함되므로 앞부분을 제외하고 답변만
        # 사람이 읽을 수 있는 문자열로 바꿉니다.
        return self.tokenizer.decode(
            output[0, inputs.shape[-1] :], skip_special_tokens=True
        ).strip()


# local_entrypoint는 Modal 실행 명령이 내 컴퓨터에서 시작할 함수입니다.
@app.local_entrypoint()
def main() -> None:
    """터미널 입력을 받고 원격 모델 호출을 연결합니다."""
    from modal_chat.cli import run_chat

    # ChatModel()은 원격 클래스의 호출용 객체를 만듭니다. 실제 답변 생성은
    # .remote(prompt)를 호출할 때 Modal의 GPU에서 일어납니다.
    model = ChatModel()
    # lambda는 질문을 받아 원격 generate()를 호출하는 짧은 함수입니다.
    # run_chat()은 이 함수를 사용해 터미널의 질문을 Modal에 보냅니다.
    run_chat(lambda prompt: model.generate.remote(prompt))
