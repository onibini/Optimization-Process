# 업데이트 보고서: GitHub 메인 페이지(README) 개편과 사용 설명서

- 날짜: 2026-10-23
- 범위: `README.md`(재작성), `docs/manual_ko.md`(신규), `docs/images/overview.png`(신규)

## 1. 개요

GitHub 저장소 첫 화면을 보기 좋게 다듬고, 프로그램 사용 설명서를 추가했다(사용자 요청). 코드는 바뀌지 않았다.

## 2. 변경 내용

- **README.md**(영문, GitHub 첫 화면): 제목과 한 줄 소개, 배지(CI 상태, Python, WAMIT, ruff, MIT), 개요 그림, "왜 이 프로젝트인가", 주요 기능 표, 계산 흐름도(Mermaid), 빠른 시작, 설정 요약 표, 결과(논문 최적해 재현 표, 회전 벤치마크 그림), 폴더 구조, 문서 링크, 개발, 인용(논문, BibTeX), 라이선스.
- **docs/manual_ko.md**(한국어 사용 설명서, 명령은 cmd 기준): 개요, 설치, 빠른 시작, `config.cfg` 전 항목 표(섹션별), 해역 데이터, 실행 화면 읽기(Hits·WAMIT·Penalty, 경고), 결과 파일, 원격 실행, 실험·검증 스크립트 표, 권장 설정, 문제 해결, 자주 묻는 질문.
- **docs/images/overview.png**: 평면도(수직벽 앞 5기 배열, 탐색 영역, 입사파)와 측면도(원통 + 반구, R·D·총 흘수, heave, PTO).

![개요 그림](../images/overview.png)

## 3. 호환성 영향

없음(문서만).

## 4. 검증

- README와 설명서의 설정 값·기본값·경고 문구·명령을 현재 코드(`config.cfg`, `main.py`, `src/utils/geometry.py` 등)와 대조했다. 예: `MinSpacing`은 WEC 중심 사이 최소 거리 = `MinSpacing` × R.
- 문서 안 링크(설명서 목차 앵커, README → 설명서 섹션)는 GitHub 앵커 규칙에 맞췄다.
- 단위 테스트, `ruff check .`, `ruff format --check .` 통과(코드 변경 없음).

## 5. 남은 이슈 / 후속 작업

- GitHub 저장소 소개(About)와 주제(topics) 설정은 푸시 때 사용자 확인 후 `gh repo edit`로 할 수 있다.
- 영문 설명서, GitHub Pages(문서 사이트)는 필요하면 추가.
