# exam-question-reviewer

문항 이미지 한 장을 보고 출제 오류를 판단하는 CLI입니다. 앞 앱 `exam-pdf-splitter`가 만든 PNG를 그대로 사용할 수 있습니다. 공통 지문을 포함한 문항은 지문과 문항이 함께 있는 PNG를 입력하세요.

## 실행

Python 3.12와 uv가 필요합니다. `OPENAI_API_KEY`를 환경 변수로 설정하고 저장소 루트에서 실행하세요. 기본 모델은 `gpt-5.4-mini`이며 추론 강도는 `medium`입니다. `--model`로 이미지 입력과 Structured Outputs를 지원하는 모델을 지정할 수 있습니다. 문항 이미지는 OpenAI API에 전송되며 API 사용료가 적용됩니다.

```sh
# 한 문항 검수
uv run --package exam-question-reviewer exam-question-reviewer ./exam-questions/question-001.png

# 폴더 내 문항 전체를 검수하고 JSON으로 저장
uv run --package exam-question-reviewer exam-question-reviewer ./exam-questions > ./review.json
```

PNG, JPEG, WebP, 정지 GIF를 지원합니다. 파일 여러 개나 이미지 폴더를 입력할 수 있으며, 이미지마다 독립적으로 한 문항을 검수합니다. JSON은 표준 출력, 진행 상황은 표준 오류로 표시합니다. 개별 파일 처리에 실패하면 해당 항목을 `error`로 남기고 나머지를 계속 검수하며 종료 코드는 1입니다.

## 판정

| 값 | 의미 |
| --- | --- |
| `issue_found` | 확인된 출제 오류가 있습니다. 오류 유형, 위치, 이미지에 보이는 근거와 설명을 반환합니다. |
| `no_issue_found` | 주어진 이미지에서 문제를 풀고 보기를 검토한 결과 오류를 발견하지 못했습니다. |
| `needs_review` | 이미지가 흐리거나 잘렸거나, 지문이나 자료가 부족해 사람이 확인할 부분이 있습니다. |

`answer_candidates`는 이미지 속 문항을 직접 풀어 얻은 답 후보입니다. `summary`는 판정의 요약 근거이고 `limitations`는 추가 확인이 필요한 내용입니다. 공식 정답표와의 대조는 현재 검수 범위에 포함되지 않습니다.
