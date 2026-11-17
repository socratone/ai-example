import argparse
import json
from pathlib import Path
import sys

from modal.exception import Error as ModalError

from .app import ExamReviewer, app

from .reviewer import DEFAULT_MODEL, ReviewError, review_image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def collect_paths(inputs: list[Path]) -> list[Path]:
    paths = []
    for path in inputs:
        if path.is_dir():
            images = sorted(
                candidate
                for candidate in path.iterdir()
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES
            )
            if not images:
                raise ReviewError(f"No images found in {path}.")
            paths.extend(images)
        elif path.is_file():
            paths.append(path)
        else:
            raise ReviewError(f"Input does not exist or is not a regular file: {path}")
    return list(dict.fromkeys(path.resolve() for path in paths))


def main() -> int:
    parser = argparse.ArgumentParser(description="Review exam questions, one image per question.")
    parser.add_argument("input", type=Path, nargs="+", help="question images or directories of images")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"vision model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    try:
        paths = collect_paths(args.input)
    except (OSError, ReviewError) as exc:
        parser.error(str(exc))

    results = []
    failed = False
    print("Starting the Modal review app.", file=sys.stderr)
    try:
        with app.run():
            model = ExamReviewer(model_id=args.model)
            for path in paths:
                print(f"Reviewing {path.name}", file=sys.stderr)
                try:
                    review = review_image(model.generate.remote, path)
                    results.append({"image": str(path), "review": review.model_dump(mode="json")})
                except ReviewError as exc:
                    print(f"{path.name}: {exc}", file=sys.stderr)
                    results.append({"image": str(path), "error": str(exc)})
                    failed = True
    except ModalError as exc:
        print(f"Modal app failed: {exc}", file=sys.stderr)
        failed = True

    print(json.dumps({"model": args.model, "results": results}, ensure_ascii=False, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
