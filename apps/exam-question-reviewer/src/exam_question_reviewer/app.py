"""Run the exam image reviewer on Modal GPUs."""

from io import BytesIO

import modal
from PIL import Image, ImageOps

from .reviewer import DEFAULT_MODEL, REVIEW_INSTRUCTIONS, Review

CACHE_DIR = "/model-cache"
app = modal.App("ai-example-exam-question-reviewer")
cache = modal.Volume.from_name("ai-example-exam-review-model-cache", create_if_missing=True)
image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.13.0", "pillow>=11,<14", "pydantic>=2,<3")
    .env({"HF_HOME": CACHE_DIR})
    .add_local_python_source("exam_question_reviewer")
)


@app.cls(image=image, gpu="L40S", volumes={CACHE_DIR: cache}, startup_timeout=1800, timeout=300)
class ExamReviewer:
    model_id: str = modal.parameter(default=DEFAULT_MODEL)

    @modal.enter()
    def load(self) -> None:
        from vllm import LLM, SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        self.model = LLM(
            model=self.model_id,
            dtype="bfloat16",
            enforce_eager=True,
            max_model_len=8192,
            max_num_seqs=1,
            limit_mm_per_prompt={"image": 1, "video": 0},
            mm_processor_kwargs={"size": {"longest_edge": 2_500_000, "shortest_edge": 3_136}},
        )
        cache.commit()
        self.sampling = SamplingParams(
            temperature=0,
            max_tokens=2048,
            structured_outputs=StructuredOutputsParams(json=Review.model_json_schema()),
        )

    @modal.method()
    def generate(self, image_bytes: bytes) -> str:
        with Image.open(BytesIO(image_bytes)) as source:
            normalized = ImageOps.exif_transpose(source).convert("RGBA")
        question_image = Image.new("RGB", normalized.size, "white")
        question_image.paste(normalized, mask=normalized.getchannel("A"))

        messages = [
            {"role": "system", "content": REVIEW_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "image_pil", "image_pil": question_image},
                    {"type": "text", "text": "이미지 속 시험 문항 하나를 검수하고 결과를 JSON으로 작성해 주세요."},
                ],
            },
        ]
        [result] = self.model.chat(messages, sampling_params=self.sampling, use_tqdm=False)
        [output] = result.outputs
        return output.text
