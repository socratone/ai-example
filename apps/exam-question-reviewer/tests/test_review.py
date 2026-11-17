from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from modal.exception import AuthError
from PIL import Image

from exam_question_reviewer.app import ExamReviewer, cache
from exam_question_reviewer.cli import main
from exam_question_reviewer.reviewer import DEFAULT_MODEL, ReviewError, review_image

MULTIPLE_ANSWERS = {
    "verdict": "issue_found",
    "answer_candidates": ["① 4", "③ 4"],
    "summary": "2 + 2의 답인 4가 두 보기에 있습니다.",
    "issues": [{
        "category": "multiple_correct_answers",
        "location": "보기 ①과 ③",
        "evidence": "① 4, ③ 4",
        "explanation": "단일 선택 문항에서 두 보기가 모두 맞습니다.",
    }],
    "limitations": [],
}


class ReviewTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.png = self.directory / "question-001.png"
        Image.new("RGB", (160, 120), "white").save(self.png)

    def test_validated_png_bytes_go_to_modal_method_and_yield_issue(self):
        generate = Mock(return_value=json.dumps(MULTIPLE_ANSWERS))

        review = review_image(generate, self.png)

        generate.assert_called_once_with(self.png.read_bytes())
        self.assertEqual(review.model_dump(), MULTIPLE_ANSWERS)

    def test_incomplete_evidence_is_reported_as_needs_review(self):
        report = {
            "verdict": "needs_review",
            "answer_candidates": [],
            "summary": "보기의 오른쪽 끝이 잘렸습니다.",
            "issues": [],
            "limitations": ["보기 ④의 오른쪽 끝이 보이는 원본이 필요합니다."],
        }

        self.assertEqual(review_image(lambda _: json.dumps(report), self.png).model_dump(), report)

    def test_invalid_verdict_or_truncated_json_is_a_processing_failure(self):
        for result in [json.dumps({**MULTIPLE_ANSWERS, "issues": []}), '{"verdict":']:
            with self.subTest(result=result):
                with self.assertRaisesRegex(ReviewError, "incomplete or inconsistent"):
                    review_image(lambda _: result, self.png)

    def test_remote_inference_failure_is_reported(self):
        generate = Mock(side_effect=RuntimeError("GPU unavailable"))

        with self.assertRaisesRegex(ReviewError, "Modal inference failed: GPU unavailable"):
            review_image(generate, self.png)

    def test_folder_review_skips_invalid_file_and_continues(self):
        bad_png = self.directory / "question-000.png"
        bad_png.write_bytes(b"broken")
        (self.directory / "notes.txt").write_text("Ignore this.", encoding="utf-8")
        generate = Mock(return_value=json.dumps(MULTIPLE_ANSWERS))
        model = SimpleNamespace(generate=SimpleNamespace(remote=generate))
        stdout, stderr = StringIO(), StringIO()

        with (
            patch("sys.argv", ["exam-question-reviewer", str(self.directory), str(self.png)]),
            patch("exam_question_reviewer.cli.app.run", return_value=nullcontext()) as run_app,
            patch("exam_question_reviewer.cli.ExamReviewer", return_value=model) as reviewer,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        failed, succeeded = json.loads(stdout.getvalue())["results"]
        self.assertIn("error", failed)
        self.assertEqual(succeeded["review"]["verdict"], "issue_found")
        generate.assert_called_once_with(self.png.read_bytes())
        reviewer.assert_called_once_with(model_id=DEFAULT_MODEL)
        run_app.assert_called_once()

    def test_modal_auth_failure_exits_cleanly(self):
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("sys.argv", ["exam-question-reviewer", str(self.png)]),
            patch("exam_question_reviewer.cli.app.run", side_effect=AuthError("Please run modal setup.")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("modal setup", stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["results"], [])

    def test_gpu_method_passes_image_and_json_schema_to_vllm(self):
        result = SimpleNamespace(outputs=[SimpleNamespace(text=json.dumps(MULTIPLE_ANSWERS))])
        engine = Mock()
        engine.chat.return_value = [result]
        vllm = ModuleType("vllm")
        vllm.LLM = Mock(return_value=engine)
        vllm.SamplingParams = Mock()
        sampling_params = ModuleType("vllm.sampling_params")
        sampling_params.StructuredOutputsParams = Mock()

        with (
            patch.dict("sys.modules", {"vllm": vllm, "vllm.sampling_params": sampling_params}),
            patch.object(cache, "commit"),
        ):
            output = ExamReviewer().generate.local(self.png.read_bytes())

        self.assertEqual(json.loads(output), MULTIPLE_ANSWERS)
        self.assertEqual(vllm.LLM.call_args.kwargs["model"], DEFAULT_MODEL)
        schema = sampling_params.StructuredOutputsParams.call_args.kwargs["json"]
        self.assertIn("verdict", schema["properties"])
        [messages] = engine.chat.call_args.args
        question = messages[1]["content"][0]["image_pil"]
        self.assertEqual(question.size, (160, 120))
        self.assertEqual(question.mode, "RGB")
