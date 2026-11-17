from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image
import pymupdf

from exam_pdf_splitter.splitter import SplitError, split_pdf


RED = (1, 0, 0)
GREEN = (0, 1, 0)
BLUE = (0, 0, 1)


class SplitPdfTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / "test.pdf"
        self.output = Path(temp.name) / "questions"

    def test_two_columns_follow_reading_order_and_ignore_center_rule(self):
        with pymupdf.open() as document:
            page = document.new_page(width=600, height=800)
            page.draw_line((300, 24), (300, 776))
            page.insert_text((32, 60), "1. First question")
            page.insert_text((32, 140), "2. Second question")
            page.insert_text((325, 60), "3. Third question")
            page.insert_text((325, 140), "4. Fourth question")
            page.draw_rect(pymupdf.Rect(370, 77, 382, 89), fill=BLUE, width=0)
            document.save(self.source)

        files = split_pdf(self.source, self.output, dpi=72)

        self.assertEqual([file.name for file in files], [f"question-{i:03d}.png" for i in range(1, 5)])
        with Image.open(files[1]) as image:
            self.assertLess(image.height, 50)
        self.assert_colors(files[2], include=[BLUE])
        self.assert_colors(files[0], exclude=[BLUE])

    def test_shared_passage_and_continuation_are_attached_to_the_right_questions(self):
        with pymupdf.open() as document:
            first = document.new_page()
            first.insert_text((40, 55), "[1~2] Shared passage")
            first.draw_rect(pymupdf.Rect(50, 65, 62, 77), fill=RED, width=0)
            first.insert_text((40, 110), "1. First question")
            first.draw_rect(pymupdf.Rect(55, 125, 67, 137), fill=GREEN, width=0)
            second = document.new_page()
            second.insert_text((50, 45), "First question continued")
            second.draw_rect(pymupdf.Rect(50, 55, 62, 67), fill=BLUE, width=0)
            second.insert_text((40, 110), "2. Second question")
            second.insert_text((40, 170), "3. Independent question")
            document.save(self.source)

        first, second, third = split_pdf(self.source, self.output, dpi=72)

        self.assert_colors(first, include=[RED, GREEN, BLUE])
        self.assert_colors(second, include=[RED], exclude=[GREEN, BLUE])
        self.assert_colors(third, exclude=[RED, GREEN, BLUE])

    def test_empty_detection_does_not_create_output_directory(self):
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 55), "Cover page")
            document.save(self.source)

        with self.assertRaisesRegex(SplitError, "No numbered questions found"):
            split_pdf(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        existing = self.output / "question-001.png"
        existing.write_bytes(b"existing")

        with self.assertRaisesRegex(SplitError, "Output already exists"):
            split_pdf(self.source, self.output)
        self.assertEqual(existing.read_bytes(), b"existing")

    def assert_colors(self, file, *, include=(), exclude=()):
        with Image.open(file) as image:
            entries = image.getcolors(maxcolors=4096)
            self.assertIsNotNone(entries)
            colors = {color for _, color in entries}
        for color in include:
            self.assertIn(tuple(round(channel * 255) for channel in color), colors)
        for color in exclude:
            self.assertNotIn(tuple(round(channel * 255) for channel in color), colors)
