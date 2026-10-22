# Working Rules for AI Assistants (Claude)

이 파일은 이 저장소에서 작업하는 AI 어시스턴트가 **매 작업마다** 따라야 하는 규칙입니다.
프로젝트 개요는 [README.md](README.md), 구조·알고리즘·규약은 [docs/](docs/)를 먼저 읽으세요.

## 1. 반영 방식
- 수정 사항은 프로젝트 파일 폴더(Claude Project 문서 / 저장소)에 **직접 반영**합니다.
- 별도의 zip 묶음은 만들지 않습니다.

## 2. GitHub 저장소 구조 유지
이 프로젝트는 GitHub 공개를 전제로 합니다. 파일을 추가·이동할 때 아래 구조를 지킵니다.

```
├── .github/workflows/python-tests.yml  # lint(ruff) + 테스트(Python 3.10 / 3.12)
├── .github/ISSUE_TEMPLATE/ + pull_request_template.md
├── .gitignore / .gitattributes
├── CHANGELOG.md               # 모든 변경을 [Unreleased]에 기록
├── CLAUDE.md                  # (이 파일)
├── CONTRIBUTING.md            # 기여 안내
├── LICENSE                    # MIT
├── README.md
├── main.py / config.cfg
├── requirements.txt / requirements-dev.txt / ruff.toml
├── data/                      # 입력 데이터 (env_data.csv)
├── docs/                      # 설계 문서 + reports/ (업데이트 보고서)
├── report/                    # 쉬운 말 설명 리포트 (초등학생도 이해할 수 있게, 변경마다 추가)
├── scripts/                   # remote.ps1 (원격 계산 보내기/가져오기), summarize_results.py
├── results/                   # 계산용 PC에서 가져온 결과 + summary.csv (gitignore)
├── src/                       # algorithms / problems / physics / utils
├── tests/                     # unittest, WAMIT 없이 실행 가능해야 함
├── logs/                      # 실행 결과 (gitignore)
└── workspace/                 # WAMIT 입출력 (gitignore)
```

- 실행 산출물(`logs/`, `workspace/`, `__pycache__/`)은 커밋하지 않습니다.
- 새 기능/수정에는 `tests/`에 테스트를 추가합니다. 테스트는 WAMIT 없이 돌아가야 합니다.
- 작업 완료 전 반드시 확인: `ruff check .`, `ruff format --check .`, `python -m unittest discover -s tests`.
- Python 3.10 이상을 지원합니다 (`ruff.toml`의 `target-version = "py310"`).

## 3. 업데이트 보고서 (매 업데이트 필수)
- 위치: `docs/reports/YYYY-MM-DD_NN_<짧은-제목>.md` (NN = 그날의 순번)
- 같은 내용을 `CHANGELOG.md`의 `[Unreleased]`에 요약하고 보고서 링크를 답니다.
- 보고서 목차:
  1. 개요 (무엇을 왜)
  2. 변경 내용 (항목별, 관련 파일)
  3. 호환성 영향 (설정 파일·로그 형식·API 변경, 사용자가 해야 할 일)
  4. 검증 (테스트/ruff 결과, 수정 전후 비교 등)
  5. 남은 이슈 / 후속 작업

## 3-1. 쉬운 설명 리포트 `report/` (매 업데이트 필수)
- 위치: `report/YYYY-MM-DD_NN_<짧은-제목>.md` (NN = 그날의 순번), 목차는 `report/README.md`에 한 줄 추가합니다.
- 읽는 사람은 **초등학생도 이해할 수 있게** 씁니다: 짧은 문장, 일상 비유, 어려운 말은 바로 풀이, 숫자는 표나 예시로.
- 내용: 무엇이 바뀌었는지, 왜 바꿨는지, 전과 후가 어떻게 다른지, 아직 안 풀린 문제. 잘못 알았다가 고친 것은 숨기지 말고 적습니다.
- `docs/reports/`(기술 보고서)와 별개이며 둘 다 작성합니다. 기술 보고서에는 정확한 수치와 근거를, 여기에는 이해를 돕는 설명을 씁니다.

## 4. 도메인 규칙
- **모든 설계 변수(반지름 R, 흘수 D, WEC 좌표 x/y)는 양수(> 0)만 허용합니다.**
  `config.cfg`의 탐색 범위는 `0 < Min < Max` 이어야 하며, `FixedRadius`, `FixedDraft`,
  `MinSpacing`, `StepSize`도 양수여야 합니다 (`src/utils/validation.py`).
- `Draft`는 원통부 길이이며, 총 흘수는 `Draft + Radius` 입니다 (반구 바닥).
- 물리 해석 입력(WAMIT .pot/.frc/.cfg/.gdf)을 바꾸는 변경은 보고서에 명시하고, 그렇지 않은 리팩터링은
  수정 전후 WAMIT 입력 파일이 동일함을 확인합니다.
