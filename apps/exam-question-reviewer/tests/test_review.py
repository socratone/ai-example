from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import httpx
from openai import OpenAI
from PIL import Image

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
        self.requests = []

    def client_for(self, output):
        def respond(request):
            self.requests.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={
                "id": "resp_test",
                "object": "response",
                "status": "completed",
                "created_at": 0,
                "model": DEFAULT_MODEL,
                "output": [{
                    "type": "message",
                    "id": "msg_test",
                    "role": "assistant",
                    "status": "completed",
                    "content": [output],
                }],
            })

        client = OpenAI(
            api_key="test-key",
            base_url="https://review.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            max_retries=0,
        )
        self.addCleanup(client.close)
        return client

    def output_text(self, report):
        return {"type": "output_text", "text": json.dumps(report), "annotations": []}

    def test_sends_image_only_as_source_and_parses_confirmed_issue(self):
        client = self.client_for(self.output_text(MULTIPLE_ANSWERS))

        review = review_image(client, self.png, DEFAULT_MODEL)

        self.assertEqual(review.model_dump(), MULTIPLE_ANSWERS)
        [(path, body)] = self.requests
        self.assertEqual(path, "/v1/responses")
        self.assertEqual(body["model"], DEFAULT_MODEL)
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertFalse(body["store"])
        self.assertTrue(body["text"]["format"]["strict"])
        [message] = body["input"]
        [task, source] = message["content"]
        self.assertEqual(task["type"], "input_text")
        self.assertEqual(source["type"], "input_image")
        self.assertEqual(source["detail"], "high")
        self.assertTrue(source["image_url"].startswith("data:image/png;base64,"))

    def test_incomplete_evidence_is_reported_as_needs_review(self):
        report = {
            "verdict": "needs_review",
            "answer_candidates": [],
            "summary": "보기의 오른쪽 끝이 잘렸습니다.",
            "issues": [],
            "limitations": ["보기 ④의 오른쪽 끝이 보이는 원본이 필요합니다."],
        }
        client = self.client_for(self.output_text(report))

        self.assertEqual(review_image(client, self.png, DEFAULT_MODEL).model_dump(), report)

    def test_invalid_verdict_is_a_processing_failure(self):
        report = {**MULTIPLE_ANSWERS, "issues": []}
        client = self.client_for(self.output_text(report))

        with self.assertRaisesRegex(ReviewError, "incomplete or inconsistent"):
            review_image(client, self.png, DEFAULT_MODEL)

    def test_refusal_is_a_processing_failure(self):
        client = self.client_for({"type": "refusal", "refusal": "Unable to review."})

        with self.assertRaisesRegex(ReviewError, "did not return a structured review"):
            review_image(client, self.png, DEFAULT_MODEL)

    def test_folder_review_continues_past_invalid_file(self):
        bad_png = self.directory / "question-000.png"
        bad_png.write_bytes(b"broken")
        (self.directory / "notes.txt").write_text("Ignore this.", encoding="utf-8")
        client = self.client_for(self.output_text(MULTIPLE_ANSWERS))
        stdout, stderr = StringIO(), StringIO()

        with (
            patch("sys.argv", ["exam-question-reviewer", str(self.directory), str(self.png)]),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("exam_question_reviewer.cli.OpenAI", return_value=client),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        failed, succeeded = json.loads(stdout.getvalue())["results"]
        self.assertIn("error", failed)
        self.assertEqual(succeeded["review"]["verdict"], "issue_found")
        self.assertEqual(len(self.requests), 1)
