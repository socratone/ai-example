# exam-pdf-splitter

시험지 PDF를 문항별 PNG로 분할하는 로컬 CLI입니다. 문항 본문, 수식, 그림과 선택지를 PDF에 표시된 모습 그대로 저장합니다. PDF와 문항 이미지는 로컬에서 처리합니다.

## 실행

저장소 루트에서 실행합니다. Python 3.12와 uv가 필요합니다.

```sh
uv run --package exam-pdf-splitter exam-pdf-splitter ./exam.pdf
```

기본 출력 위치는 PDF 옆의 `exam-questions/`입니다. `question-001.png`, `question-002.png`처럼 문항마다 PNG 하나를 저장합니다. 출력 폴더가 이미 있다면 새 경로를 지정하세요.

```sh
uv run --package exam-pdf-splitter exam-pdf-splitter ./exam.pdf -o ./out --columns 2
```

- 문항 번호가 줄 처음에 나오는 `1.`, `1)`, `Q1.`, `문항 1.` 같은 형식을 인식합니다.
- 기본으로 1단·2단을 감지합니다. 2단은 페이지 중앙을 기준으로 왼쪽 단, 오른쪽 단 순으로 읽습니다. 단 구성이 일정한 시험지에 맞춰져 있으며, 자동 감지가 틀리면 `--columns 1` 또는 `--columns 2`를 지정하세요.
- `[3~5]` 형태의 공통 지문을 3~5번 PNG의 위에 붙입니다. 다음 열이나 페이지로 넘어가는 문항도 각 조각을 위아래로 이어 PNG 하나로 저장합니다.
- 기본 해상도는 200 DPI입니다. 작은 수식이 있으면 `--dpi 300`을 사용하세요.
- 표지나 정답표를 건너뛰려면 `--start-page 2 --end-page 6`처럼 문항 페이지 범위를 지정하세요. 머리글·바닥글 제외 높이는 PDF 포인트 단위로 각각 기본 24입니다. 본문이 가장자리까지 이어지면 `--header 0 --footer 0`으로 조정하세요.

## 스캔 PDF

Tesseract와 해당 언어 데이터를 설치한 뒤 OCR을 켭니다. 한글 시험지는 한국어와 영어 언어 데이터가 필요합니다. `tesseract --list-langs`로 설치 상태를 확인할 수 있습니다.

```sh
uv run --package exam-pdf-splitter exam-pdf-splitter ./scan.pdf --ocr kor+eng
```

OCR 결과는 문항의 위치를 찾는 데만 사용합니다. PNG는 PDF 원본에서 렌더링합니다. 흐린 스캔이나 문항 번호가 들쭉날쭉한 시험지는 일부 문항을 놓칠 수 있으니 저장된 파일과 원본의 문항 번호를 확인하세요.
