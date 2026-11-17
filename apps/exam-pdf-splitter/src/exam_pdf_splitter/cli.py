import argparse
import math
from pathlib import Path
import sys

import pymupdf

from .splitter import SplitError, split_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Split an exam PDF into one PNG per question.")
    parser.add_argument("pdf", type=Path, help="input exam PDF")
    parser.add_argument("-o", "--output", type=Path, help="new output directory (default: <pdf stem>-questions)")
    parser.add_argument("--columns", choices=["auto", "1", "2"], default="auto")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--header", type=float, default=24, help="ignored header height in PDF points")
    parser.add_argument("--footer", type=float, default=24, help="ignored footer height in PDF points")
    parser.add_argument("--start-page", type=int, default=1, help="first PDF page to read, starting at 1")
    parser.add_argument("--end-page", type=int, help="last PDF page to read, inclusive")
    parser.add_argument("--ocr", metavar="LANG", help="run Tesseract OCR (e.g. eng or kor+eng)")
    args = parser.parse_args()
    if not 72 <= args.dpi <= 400:
        parser.error("--dpi must be between 72 and 400")
    if any(not math.isfinite(value) or value < 0 for value in (args.header, args.footer)):
        parser.error("--header and --footer must be finite, nonnegative values")

    output = args.output or args.pdf.with_name(f"{args.pdf.stem}-questions")
    try:
        files = split_pdf(
            args.pdf,
            output,
            columns=args.columns,
            dpi=args.dpi,
            header=args.header,
            footer=args.footer,
            start_page=args.start_page,
            end_page=args.end_page,
            ocr_language=args.ocr,
        )
    except (SplitError, OSError, pymupdf.FileDataError, pymupdf.EmptyFileError, pymupdf.FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for path in files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
