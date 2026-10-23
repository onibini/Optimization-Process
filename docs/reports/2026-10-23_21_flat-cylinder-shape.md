# 업데이트 보고서: 평평한 바닥 원통 WEC 형상 추가 (Shape)

- 날짜: 2026-10-23
- 범위: `src/physics/mesh_axisymmetric_shape.py`, `src/physics/wamit_handler.py`, `src/problems/*.py`, `main.py`, `config.cfg`, `tests/test_cylinder_shape.py`(신규), `README.md`, `docs/manual_ko.md`, `docs/algorithms_and_problems.md`, `docs/architecture.md`, `CLAUDE.md`

## 1. 개요

지금까지 WEC 형상은 원통 + 반구 바닥 하나였다. 사용자 요청으로 **평평한 바닥 원통**(설계 변수 R, D)을 추가했다. `config.cfg`의 `[WEC Parameters] Shape`로 고르며 기본값은 기존 형상(1)이다.

## 2. 변경 내용

- **메쉬** (`build_cylinder_panels`, `choose_cylinder_grid`, `count_cylinder_panels`, `generate_cylinder_mesh`, `generate_mesh`):
  - 1/4 모델(ISX = ISY = 1). 옆면은 2n열 × n_z행이다. 바닥 1/4 원판은 가운데 정사각형(한 변 0.55 R, n × n)과, 그 두 변(x = 0.55R, y = 0.55R)을 둘레 원호(0~45°, 45~90°)에 잇는 두 패치(각 n × m)로 나눴다. 패치 내부는 정사각형 변과 원호 사이를 선형 보간한다. m ≈ 0.45·4n/π로 정해 패널이 정사각형에 가깝게 했다.
  - 바닥 둘레는 옆면과 같은 2n칸으로 맞물린다(테스트로 확인).
  - 패널 수 = n² + 2nm + 2n·n_z. 목표(`MeshPanels`)에 가장 가까운 (n, n_z)를 원통 + 반구와 같은 방식(패널 수 오차 + 옆면 종횡비)으로 고른다.
- **형상 도구**: `SHAPES`, `check_shape`, `total_draft`(1: D + R, 2: D), `displaced_volume`.
- **WAMIT 입력**: `write_wamit_inputs`가 `config["shape"]`로 메쉬를 고른다. 메쉬 캐시 메타데이터에 형상 구분(`flat-cylinder-v1`)을 넣어, 형상이 바뀌면 GDF를 다시 만든다. 형상 1의 메타데이터와 GDF는 이전과 같다.
- **공진 주파수 어림** `heave_omega0(R, D, shape)`: 형상 1은 √(g/(D + 2R/3)), 형상 2는 √(g/D). 적응형 주파수 격자(`FreqGrid=1`)가 이를 쓴다.
- **질량·복원력**: 원래 WAMIT 출력(부피, `.hst`)에서 읽으므로 RAO·발전량 코드는 바꾸지 않았다.
- **main.py**: `Shape`를 읽어 검증하고, 시작할 때와 결과 출력에서 형상 이름과 총 흘수를 형상에 맞게 보여 준다.

![두 형상의 메쉬](images/2026-10-23_21_shapes_mesh.png)

*그림 1. 같은 총 흘수 5.5 m, 1/4 모델 120 패널. 왼쪽 형상 1(원통 + 반구), 오른쪽 형상 2(평평한 바닥 원통).*

## 3. 호환성 영향

- `Shape`가 없거나 1이면 WAMIT 입력과 결과가 이전과 같다.
- 형상 2에서 `Draft`(`DraftMin/Max`, `FixedDraft`)는 **총 흘수**를 뜻한다.

## 4. 검증

- 테스트 11건:
  - 패널 수 공식과 목표(±15%).
  - 1/4 모델의 넓이와 부피가 정확값과 1%·1.5% 이내(발산 정리). 다섯 형상(R 0.5~2.5, D 0.5~5.0)에서 실제로 넓이 0.996~0.998, 부피 0.989~0.998배다.
  - 모든 꼭짓점이 1/4 영역·옆면(r = R)·바닥(z = −D) 위에 있고, 법선은 바닥은 아래, 옆면은 바깥을 향한다.
  - 옆면과 바닥의 둘레 점이 일치한다.
  - GDF 헤더와 패널 수, 형상 선택 함수, 잘못된 입력 거부, 총 흘수·부피·공진 주파수, 프로젝트 기본값 1.
  - WAMIT 입력에서 형상 전환 시 메쉬 재생성, 잘못된 형상 거부.
- 기존 테스트 전체, `ruff check .`, `ruff format --check .` 통과.

## 5. 남은 이슈 / 후속 작업

- **WAMIT으로 확인하지 않았다.** 형상 2의 메쉬 수렴(패널 수에 따른 발전량 변화)과 반복 솔버 수렴은 계산용 PC에서 확인해야 한다. 바닥 모서리(직각)는 반구보다 수렴이 느릴 수 있다.
- **불규칙 주파수**: 평평한 바닥 원통도 내부 문제의 고유 주파수(불규칙 주파수)가 있다. R = 2.5 m에서 첫 값은 대략 √(g·2.405/R) ≈ 3.1 rad/s로, 현재 상한(3.0) 바로 위다. R이 작으면 더 높아진다. 상한을 올리면 주의해야 한다.
- 평평한 바닥의 점성(유동 박리) 감쇠는 포텐셜 유동에 들어 있지 않다.
