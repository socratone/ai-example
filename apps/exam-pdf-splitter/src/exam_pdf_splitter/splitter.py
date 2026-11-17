from dataclasses import dataclass, field
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unicodedata import normalize

from PIL import Image, ImageOps
import pymupdf

QUESTION = re.compile(r"^(?:문항\s*|문제\s*|Q\s*)?(\d{1,3})\s*[.)](?!\d)", re.IGNORECASE)
PASSAGE = re.compile(r"^\[\s*(\d{1,3})\s*[~∼–—-]\s*(\d{1,3})\s*\]")
MARKER_PADDING = 2
MARKER_INDENT = 14


class SplitError(Exception):
    """The PDF cannot be split with the current settings."""


@dataclass(frozen=True)
class Marker:
    first: int
    last: int | None
    x: float
    y: float


@dataclass(frozen=True)
class Crop:
    page: int
    rect: pymupdf.Rect


@dataclass
class Block:
    marker: Marker
    crops: list[Crop] = field(default_factory=list)


def page_markers(
    page: pymupdf.Page,
    top: float,
    bottom: float,
    ocr_language: str | None,
) -> list[Marker]:
    text_page = None
    if ocr_language:
        try:
            text_page = page.get_textpage_ocr(language=ocr_language, dpi=250, full=True)
        except (RuntimeError, ValueError) as exc:
            raise SplitError(
                f"Page {page.number + 1}: OCR failed. Check Tesseract and its "
                f"'{ocr_language}' language data. {exc}"
            ) from exc

    markers = []
    page_data = page.get_text(
        "dict",
        flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES,
        textpage=text_page,
    )
    for block in page_data["blocks"]:
        for line in block.get("lines", []):
            rect = pymupdf.Rect(line["bbox"]) * page.rotation_matrix
            if not top <= rect.y0 < bottom:
                continue
            line_text = normalize("NFKC", "".join(span["text"] for span in line["spans"])).lstrip()
            if match := PASSAGE.match(line_text):
                first, last = map(int, match.groups())
                if 0 < first <= last:
                    markers.append(Marker(first, last, rect.x0, rect.y0))
            elif (match := QUESTION.match(line_text)) and int(match[1]) > 0:
                markers.append(Marker(int(match[1]), None, rect.x0, rect.y0))
    return markers


def looks_two_column(markers: list[Marker], width: float) -> bool:
    questions = [marker for marker in markers if marker.last is None]
    return (
        any(marker.x < width * 0.28 for marker in questions)
        and any(width * 0.50 <= marker.x < width * 0.73 for marker in questions)
    )


def lane_markers(markers: list[Marker], left: float, right: float) -> list[Marker]:
    candidates = [marker for marker in markers if left <= marker.x < right]
    starts = [marker.x for marker in candidates if marker.last is None]
    if starts:
        margin = min(starts)
        candidates = [
            marker
            for marker in candidates
            if marker.last is not None or marker.x <= margin + MARKER_INDENT
        ]
    return sorted(candidates, key=lambda marker: marker.y)


def collect_blocks(
    pages: list[tuple[pymupdf.Page, list[Marker]]],
    columns: str,
    header: float,
    footer: float,
) -> list[Block]:
    # Apply the detected layout to the exam, including continuation-only pages.
    two_columns = columns == "2" or (
        columns == "auto" and any(looks_two_column(markers, page.rect.width) for page, markers in pages)
    )
    blocks = []
    current = None
    for page, markers in pages:
        box = page.rect
        top = box.y0 + header
        bottom = box.y1 - footer
        middle = box.x0 + box.width / 2
        lanes = [(box.x0, middle), (middle, box.x1)] if two_columns else [(box.x0, box.x1)]
        for left, right in lanes:
            crop_left = left + 3 if left == middle else left
            crop_right = right - 3 if right == middle else right
            cursor = top
            for marker in lane_markers(markers, left, right):
                boundary = max(top, marker.y - MARKER_PADDING)
                if current is not None and cursor < boundary:
                    current.crops.append(Crop(page.number, pymupdf.Rect(crop_left, cursor, crop_right, boundary)))
                current = Block(marker)
                blocks.append(current)
                cursor = boundary
            if current is not None and cursor < bottom:
                current.crops.append(Crop(page.number, pymupdf.Rect(crop_left, cursor, crop_right, bottom)))
    return blocks


def render_crop(document: pymupdf.Document, crop: Crop, dpi: int) -> Image.Image | None:
    pixmap = document[crop.page].get_pixmap(dpi=dpi, clip=crop.rect)
    pixels = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    # Ignore nearly white scan background when finding the vertical content bounds.
    bounds = ImageOps.invert(pixels.convert("L")).point(lambda value: 255 if value > 35 else 0).getbbox()
    if bounds is None:
        return None
    top = max(0, bounds[1] - 8)
    bottom = min(pixels.height, bounds[3] + 8)
    return pixels.crop((0, top, pixels.width, bottom))


def save_question(
    document: pymupdf.Document,
    crops: list[Crop],
    path: Path,
    dpi: int,
) -> None:
    images = []
    for crop in crops:
        image = render_crop(document, crop, dpi)
        if image is not None:
            images.append(image)
    if not images:
        raise SplitError(f"{path.stem}: the detected area is blank.")

    gap = round(dpi / 12)
    width = max(image.width for image in images)
    height = sum(image.height for image in images) + gap * (len(images) - 1)
    combined = Image.new("RGB", (width, height), "white")
    y = 0
    for image in images:
        combined.paste(image, (0, y))
        y += image.height + gap
    combined.save(path, dpi=(dpi, dpi))


def split_pdf(
    source: Path,
    output: Path,
    *,
    columns: str = "auto",
    dpi: int = 200,
    header: float = 24,
    footer: float = 24,
    start_page: int = 1,
    end_page: int | None = None,
    ocr_language: str | None = None,
) -> list[Path]:
    if output.exists() or output.is_symlink():
        raise SplitError(f"Output already exists: {output}")

    with pymupdf.open(source, filetype="pdf") as document:
        if document.needs_pass:
            raise SplitError("The PDF is password-protected.")
        last_page = document.page_count if end_page is None else end_page
        if not 1 <= start_page <= last_page <= document.page_count:
            raise SplitError(f"Use an inclusive page range within 1–{document.page_count}.")

        pages = []
        for page in document.pages(start_page - 1, last_page):
            top = page.rect.y0 + header
            bottom = page.rect.y1 - footer
            if top >= bottom:
                raise SplitError(f"Page {page.number + 1}: header and footer leave no content area.")
            markers = page_markers(page, top, bottom, ocr_language)
            pages.append((page, markers))
        blocks = collect_blocks(pages, columns, header, footer)
        questions = [block for block in blocks if block.marker.last is None]
        if not questions:
            raise SplitError("No numbered questions found. For scanned PDFs, try --ocr eng or --ocr kor+eng.")
        numbers = [block.marker.first for block in questions]
        if len(set(numbers)) != len(numbers):
            raise SplitError(
                "Duplicate question numbers detected. Check --columns and header/footer margins, "
                "or select one section with --start-page and --end-page."
            )

        passages = [block for block in blocks if block.marker.last is not None]
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent) as temp:
            staged = Path(temp) / "questions"
            staged.mkdir()
            filenames = []
            for question in questions:
                number = question.marker.first
                shared_crops = []
                for passage in passages:
                    start, end = passage.marker.first, passage.marker.last
                    if end is not None and start <= number <= end:
                        shared_crops.extend(passage.crops)
                filename = f"question-{number:03d}.png"
                save_question(document, [*shared_crops, *question.crops], staged / filename, dpi)
                filenames.append(filename)
            staged.rename(output)
    return [output / filename for filename in filenames]
