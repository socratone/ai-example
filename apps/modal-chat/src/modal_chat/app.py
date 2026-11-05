"""Modal inference and local chat entrypoint."""

import modal

MODEL_ID = "Qwen/Qwen3-1.7B"
CACHE_DIR = "/model-cache"

app = modal.App("ai-example-modal-chat")
cache = modal.Volume.from_name("ai-example-modal-chat-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("torch", "transformers>=4.51,<5", "huggingface_hub")
    .env({"HF_HOME": CACHE_DIR})
)


@app.cls(image=image, gpu="L4", volumes={CACHE_DIR: cache}, timeout=600)
class ChatModel:
    @modal.enter()
    def load(self) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto").to(
            "cuda"
        )
        self.model.eval()
        cache.commit()

    @modal.method()
    def generate(self, prompt: str) -> str:
        import torch

        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_tensors="pt",
        ).to("cuda")
        with torch.inference_mode():
            output = self.model.generate(
                inputs,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(
            output[0, inputs.shape[-1] :], skip_special_tokens=True
        ).strip()


@app.local_entrypoint()
def main() -> None:
    from modal_chat.cli import run_chat

    model = ChatModel()
    run_chat(lambda prompt: model.generate.remote(prompt))
