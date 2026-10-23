# Changelog

이 프로젝트의 모든 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며, 각 항목의 자세한 내용은 `docs/reports/`의 보고서를 참고하세요.

## [Unreleased]

### 2026-10-23 — 평평한 바닥 원통 검증(반해석해, Haskind, 에너지 관계)
보고서: [docs/reports/2026-10-23_23_cylinder-validation.md](docs/reports/2026-10-23_23_cylinder-validation.md)

#### Added
- `scripts/experiments/cylinder_validation.py`: 고유함수 정합 반해석해(Yeung 방법)로 A33·B33, Haskind 대 산란 가진력, B33 = k|X3|²/(4ρgC_g), 흡수 한계를 WAMIT(1기)과 비교. 800 패널에서 A33·B33 0.7%, Haskind 0.12%, 에너지 관계 0.3% 이내. `tests/test_cylinder_validation.py`(6건).

### 2026-10-23 — 평평한 바닥 원통 1기 메쉬 시험(WAMIT, 이 PC)과 메쉬 개선
보고서: [docs/reports/2026-10-23_22_cylinder-mesh-check.md](docs/reports/2026-10-23_22_cylinder-mesh-check.md)

#### Added
- `scripts/experiments/shape_mesh_check.py`(1기 개방 해역, 패널 수별 부피·복원력·발전량, `--freq-grid`, `--dump`). `main.py`가 탐색 범위의 공진이 주파수 상한 위에 있으면 시작할 때 경고(`highest_heave_omega0`).

#### Changed
- 평평한 바닥 원통 메쉬의 옆면 행과 바닥 둘레 층을 바닥 모서리 쪽으로 촘촘하게(사인 간격). 120 패널에서 발전량 오차 약 1% 이내(적응형 격자, 800 패널 대비).

### 2026-10-23 — 평평한 바닥 원통 WEC 형상 추가 (Shape)
보고서: [docs/reports/2026-10-23_21_flat-cylinder-shape.md](docs/reports/2026-10-23_21_flat-cylinder-shape.md)

#### Added
- `config.cfg [WEC Parameters] Shape`: 1 원통 + 반구(기본), 2 평평한 바닥 원통(설계 변수 R, D; D = 총 흘수). 1/4 모델 메쉬(바닥은 가운데 정사각형 + 둘레 패치), 형상별 공진 주파수 어림(적응형 격자), 메쉬 캐시 구분. `tests/test_cylinder_shape.py`(11건). WAMIT 수렴 확인은 아직.

### 2026-10-23 — 사용 설명서를 일반 사용자용으로 다시 쓰기
보고서: [docs/reports/2026-10-23_20_general-manual.md](docs/reports/2026-10-23_20_general-manual.md)

#### Changed
- `docs/manual_ko.md`: 작성자 전용 내용(계산용 PC 원격 실행 절차, 논문 번호 대응, 논문 비교 설정)을 빼고 계산 과정, 변수·번호 규칙, 설치, 해역 추가, 범용 팁을 보강. README의 원격 실행 표현을 선택 사항으로.

### 2026-10-23 — GitHub 메인 페이지(README) 개편과 사용 설명서
보고서: [docs/reports/2026-10-23_19_readme-and-manual.md](docs/reports/2026-10-23_19_readme-and-manual.md)

#### Changed
- `README.md` 재작성(배지, 개요 그림, 흐름도, 설정 요약, 결과, 인용). `docs/manual_ko.md`(한국어 사용 설명서) 추가. `docs/images/overview.png`.

### 2026-10-23 — 변수끼리 얽힌(회전) 벤치마크로 최적화 알고리즘 다시 비교
보고서: [docs/reports/2026-10-23_18_rotated-benchmark.md](docs/reports/2026-10-23_18_rotated-benchmark.md)

#### Added
- `algorithm_benchmark.py --rotate`(회전 함수). 결과(WEC 격자, 평가 20,000회): 평균 순위 CMA-ES 2.4, PSO 2.5, DE 2.6, DEPSO 3.0, GA 4.5. GA의 이전 강점은 분리 가능 함수 때문이었음.

### 2026-10-23 — 해역 스펙트럼에 맞춘 주파수 범위 줄이기 검토
보고서: [docs/reports/2026-10-23_17_omega-band-assessment.md](docs/reports/2026-10-23_17_omega-band-assessment.md)

#### Changed
- 검토만(코드 변경 없음). 스펙트럼이 최대값의 0.1% 미만인 아래쪽 주파수를 빼도 발전량 손실 < 0.0005%(점 2~7개 감소, NCPU=8에서 시간 0~14% 단축). 위쪽은 작은 부표의 고주파 공진 때문에 자르면 안 됨(최대 25.7% 손실).

### 2026-10-23 — WAMIT 동시 실행(Workers)과 동기식 DE 옵션
보고서: [docs/reports/2026-10-23_16_parallel-wamit.md](docs/reports/2026-10-23_16_parallel-wamit.md)

#### Added
- `CachedEvaluator.evaluate_batch`: 캐시에 없는 설계점을 `Workers`개 WAMIT으로 동시에 평가(작업 폴더 `workspace/w<k>`, 결과·로그는 하나씩 평가한 것과 같음). 초기 개체군(모든 알고리즘)과 GA·CMA-ES 세대에 적용. `config.cfg` `Workers`(기본 1), `DEUpdate`(기본 0 = 즉시 교체, 1 = 세대 단위 DE). `scripts/experiments/parallel_wamit_bench.py`(계산용 PC 처리량 측정). 테스트 7건.

### 2026-10-23 — 최적화 알고리즘 점검과 CMA-ES c_σ 수정
보고서: [docs/reports/2026-10-23_15_optimizer-review.md](docs/reports/2026-10-23_15_optimizer-review.md)

#### Fixed
- CMA-ES 보폭 학습률 c_σ를 교과서 식 `(mu_eff + 2) / (N + mu_eff + 5)`로(이전 `(mu_eff + 2) / (N + mu)`). 벤치마크 12개 경우에서 유의한 차이 없음. 다른 알고리즘은 점검 결과만 기록.

### 2026-10-23 — 파랑 스펙트럼 기본값을 JONSWAP ITTC로, Pierson-Moskowitz 추가
보고서: [docs/reports/2026-10-23_14_wave-spectrum-default.md](docs/reports/2026-10-23_14_wave-spectrum-default.md)

#### Changed
- `config.cfg` `WaveSpec` 기본 2(Goda) → **1(ITTC)**. 같은 설계의 발전량이 약 8% 낮아짐(논문 수치와 일치). `main.py`가 `WaveSpec`을 검증.

#### Added
- `WaveSpec=3` Pierson-Moskowitz(Bretschneider 형식). `tests/test_wave_spectrum.py`(7건).

### 2026-10-23 — CMA-ES 변수별 최소 탐색 폭 시험과 3개 해역 재제출
보고서: [docs/reports/2026-10-23_13_cmaes-minstd-and-rerun.md](docs/reports/2026-10-23_13_cmaes-minstd-and-rerun.md)

#### Added
- `src/algorithms/cma_es.py`: `raise_min_std`, `min_std_factor`(기본 0, 끔; 시험 결과 효과 없음). `algorithm_benchmark.py --grid 0`(WEC 문제의 변수별 격자). 계산용 PC 작업 `20261023_190757_cmaes_sites2`(수정된 CMA-ES로 재제출).

### 2026-10-23 — CMA-ES 보폭 상한과 넘침 방지
보고서: [docs/reports/2026-10-23_12_cmaes-sigma-cap.md](docs/reports/2026-10-23_12_cmaes-sigma-cap.md)

#### Fixed
- `src/algorithms/cma_es.py`: 보폭 갱신의 한 세대 로그 변화량을 1.0 이하로, 보폭을 [격자 한 칸, 1.0]으로 제한(`update_sigma`, exp overflow 방지). `SigmaInit`은 (0, 1]만 허용. `tests/test_cma_es_sigma.py`(5건).

### 2026-10-23 — DEPSO 추가와 최적화 알고리즘 벤치마크
보고서: [docs/reports/2026-10-23_11_depso-and-optimizer-benchmark.md](docs/reports/2026-10-23_11_depso-and-optimizer-benchmark.md)

#### Added
- `src/algorithms/depso.py` (`Algorithm=5`, F·CR·w·c1·c2): 사용자의 DEPSO(Lee, Heo, Koo, 2026, Ocean Engineering 355, 125173) 갱신 규칙(PSO 이동점을 기준으로 DE 교차, 탐욕 선택). 비교용 `update="pbest"`, `"move"`. `tests/test_depso.py`.
- `scripts/experiments/algorithm_benchmark.py`: 프로젝트 최적화기를 같은 평가 횟수로 벤치마크 함수에서 비교(병렬, 그림). 결과: 평균 순위 CMA-ES 2.67, DE 2.75, PSO 3.33, DEPSO 3.42, GA 4.42; DEPSO는 원래 규칙이 변형(pbest, move)보다 좋음.

### 2026-10-23 — DE 교체 방식(즉시 교체 대 세대 단위) 벤치마크
보고서: [docs/reports/2026-10-23_10_de-update-rule-benchmark.md](docs/reports/2026-10-23_10_de-update-rule-benchmark.md)

#### Added
- `scripts/experiments/de_update_benchmark.py`: 프로젝트 DE(즉시 교체)와 세대 단위 DE를 벤치마크 함수 6개로 비교(병렬 실행, 그림). `tests/test_de_update_benchmark.py`(5건, 즉시 교체가 `run_de`와 같은지 포함). 결과: 즉시 교체가 11/24 경우 유의하게 좋고 나머지는 차이 없음, 세대 단위는 같은 품질에 약 1.15배 세대 필요.
- `CLAUDE.md`: 보고서에 가능하면 이미지를 넣는 규칙(`docs/reports/images/`, `report/images/`).

### 2026-10-23 — CMA-ES 설정 시험과 3개 해역 동시최적화 제출
보고서: [docs/reports/2026-10-23_09_cmaes-tuning-and-run.md](docs/reports/2026-10-23_09_cmaes-tuning-and-run.md)

#### Added
- `scripts/experiments/run_sites.py`: 한 작업에서 여러 해역을 순서대로 `main.main`으로 실행. `tests/test_run_sites.py`(3건).
- 가짜 목적함수 시험 결과 CMA-ES 개체 수 72, σ0 0.3 선택(표준 9는 국소해에 갇힘). 계산용 PC 작업 `20261023_161543_cmaes_sites` 제출(ITTC, 72 × 300).

### 2026-10-23 — 영일만항 수심 33 m 결과를 검증 기준에서 제거
보고서: [docs/reports/2026-10-23_08_remove-yeongil-33m.md](docs/reports/2026-10-23_08_remove-yeongil-33m.md)

#### Removed
- `docs/validation/paper_check_reference.csv`의 영일만항 33 m 행(192 → 144행), `paper_check.py --depths`와 `OLD_DEPTHS`. 영일만항의 정답 수심은 13 m.

### 2026-10-23 — 검증 기준 결과 정리 (docs/validation)
보고서: [docs/reports/2026-10-23_07_validation-reference.md](docs/reports/2026-10-23_07_validation-reference.md)

#### Added
- `docs/validation/`: 논문 최적해 재현 결과 기준 CSV와 사용법. `paper_check.py --reference <csv> [--tolerance 0.2]`로 파일 변경 후 총 발전량 변화를 확인.

### 2026-10-23 — 논문 최적해 재현 확인 결과
보고서: [docs/reports/2026-10-23_06_paper-check-result.md](docs/reports/2026-10-23_06_paper-check-result.md)

#### Changed
- `paper_check.py`에 가진력·스펙트럼·적분·수심 조합 진단 추가. 결과: 현재 기본(Goda, 영일만항 13 m)은 논문 대비 +8%/+32%. ITTC + Simpson이 -1~0%로 일치하고 영일만항은 수심 33 m에서만 일치. 현재 Goda 식은 Hs를 4.1% 크게 준다. 코드는 바꾸지 않았고 사용자 판단 대기.

### 2026-10-23 — 논문 최적해 재현 확인 도구 (paper_check.py)
보고서: [docs/reports/2026-10-23_05_paper-check-tool.md](docs/reports/2026-10-23_05_paper-check-tool.md)

#### Added
- `scripts/experiments/paper_check.py`: 논문 Table 4의 최적해 6개를 `evaluate_joint`로 평가해 논문 발전량과 비교(변형 base/fg/mesh200/mesh200fg). `tests/test_paper_check.py`(5건). 아직 계산용 PC에서 실행하지 않음.

### 2026-10-23 — 적응형 주파수 격자 옵션 FreqGrid (기본 끔)
보고서: [docs/reports/2026-10-23_04_freq-grid-option.md](docs/reports/2026-10-23_04_freq-grid-option.md)

#### Added
- `config.cfg [WAMIT Settings] FreqGrid`(0 균일 / 1 적응형): 공진 부근 0.85~1.1 x w0만 0.00625 간격, 1.5 x w0 위는 0.1 간격. `wamit_handler.adaptive_omegas`, `heave_omega0`, `check_freq_grid`, `write_pot_file(..., omegas)`(명시적 주파수 목록).
- `summary.csv`에 `freq_grid` 열. `tests/test_freq_grid_option.py`(14건).

#### Changed
- 기본값(0)에서는 WAMIT 입력이 이전과 동일.

### 2026-10-23 — 주파수 격자 검증 4차(grids --quick, 공진 폭 2단계 격자) 결과 분석
보고서: [docs/reports/2026-10-23_03_freq-grid-quick4-study.md](docs/reports/2026-10-23_03_freq-grid-quick4-study.md)

#### Changed
- 분석만 수행(코드 변경 없음). `two_stage_fwhm6`은 4개 형상 모두 기준 (a) 통과(정확도·시간), 좁은 공진(R=0.5, D=2.0)은 0.003125 확인 격자 대비 0.01%/0.013%. `two_stage_fwhm10`은 시간 기준 1건 실패. 적응형 0.85~1.1 + 미세 0.00625가 비용은 더 낮고 확인 격자 대비로는 (0.5, 2.0)도 통과하므로, 2단계의 이점은 강건성이다. 구현 대상은 사용자 결정 대기.

### 2026-10-23 — 주파수 격자 시험 도구 3차 개정 (공진 폭에 맞춘 2단계 격자, B_pto 보간 제거)
보고서: [docs/reports/2026-10-23_02_study-tool-two-stage.md](docs/reports/2026-10-23_02_study-tool-two-stage.md)

#### Added
- `scripts/experiments/freq_grid_study.py`: 2단계 후보 `two_stage_fwhm6`/`two_stage_fwhm10`(1단계 균일 0.05 결과에서 WEC별 공진 위치·폭 추정 → 폭/n 간격으로 2단계 주파수 추가, 시간·점 수는 1+2단계 합산), 새 열 `stage2_step`/`n_stage2`/`fwhm_est_min`/`fwhm_meas_min`. 가짜 WAMIT로 전체 `grids --quick`를 돌리는 통합 테스트 포함.

#### Removed
- 시험 도구의 `B_pto` 포물선 보간(`interp`) 후보와 관련 코드·열·테스트(효과 없음). `src/`는 변경 없음.

### 2026-10-23 — 주파수 격자 검증 3차(grids --quick, 구간 상단 1.1, 확인 격자, B_pto 보간) 결과 분석
보고서: [docs/reports/2026-10-23_01_freq-grid-quick3-study.md](docs/reports/2026-10-23_01_freq-grid-quick3-study.md)

#### Verified
- 계산용 PC에서 `grids --quick` 3차 실행(14.8분, `reimpl_check` 2.2e-16). 적응형 `0.85~1.1`(꼬리 0.1)은 3개 형상에서 기준 (a)를 만족(총 0.02%, 개별 WEC 0.22% 이내)하고 정확도 동등 균일 격자보다 2~4배, 현재 기본 격자 대비 시간은 1.10~1.65배. 구간 상단 1.0 → 1.1배로 개별 WEC 오차 감소. R=0.5·D=2.0은 공진 반치폭 0.03~0.04라 간격 0.00625 이하가 필요하고, 0.00625 기준격자 자체가 0.003125 대비 총 0.07%, 개별 WEC 0.28% 오차. `B_pto` 포물선 보간(`interp`)은 개별 WEC 오차를 줄이지 못해 `src/` 적용 효과 없음. 코드 변경 없음.

### 2026-10-22 — 주파수 격자 시험 도구 2차 개정 (구간 상단 1.1, 0.003125 확인 격자, B_pto 포물선 보간)
보고서: [docs/reports/2026-10-22_09_study-tool-update2.md](docs/reports/2026-10-22_09_study-tool-update2.md)

#### Added
- `scripts/experiments/freq_grid_study.py`: 적응형 `0.85~1.1`(미세 0.0125/0.00625) 후보, R=0.5·D=2.0용 `check_uniform_0.003125` 확인 격자, 비제어 RAO 피크의 포물선 보간으로 `B_pto`를 구하는 `interp` 방식(`rao_calc` 재구현 `rao_with_bpto`, `src/`는 변경 없음). 같은 WAMIT 실행에서 `node`/`interp`를 모두 계산해 방식별로 판정(`+interp`)하고 `reimpl_check`로 재구현 일치를 기록. 테스트 17건.

### 2026-10-22 — 주파수 격자 검증 2차(grids --quick, 기준 (a)) 결과 분석
보고서: [docs/reports/2026-10-22_08_freq-grid-quick2-study.md](docs/reports/2026-10-22_08_freq-grid-quick2-study.md)

#### Verified
- 계산용 PC에서 개정한 `grids --quick` 실행(11.4분). 기준 (a)(총 0.1%, 개별 WEC 0.3%, 시간은 정확도 동등 균일 격자와 비교)에서 균일 0.05/0.025는 0/4, 균일 0.0125와 적응형 후보(`0.85~1.0` 등)는 3/4 통과. 적응형 `0.85~1.0`은 51~106점으로 현재 기본 격자 대비 시간 0.87~1.41배, 정확도 동등 균일 격자보다 1.6~4배 빠름. 현재 격자의 오차는 대부분 `B_pto`가 격자 점에 걸려 달라지는 데서 옴(최대 -16%). R=0.5, D=2.0은 모든 격자가 불합격. 코드 변경 없음.

### 2026-10-22 — 주파수 격자 시험 도구 개정 (기준 (a), 좁은 구간, 0.00625 기준격자, 덤프)
보고서: [docs/reports/2026-10-22_07_study-tool-update.md](docs/reports/2026-10-22_07_study-tool-update.md)

#### Changed
- `scripts/experiments/freq_grid_study.py`: 판정 기준 (a)(정확도 0.1%/0.3% 우선, 시간은 같은 정확도의 균일 격자와 비교)로 변경하고 판정 CSV와 요약 표 추가. 기준격자를 0.00625 간격으로, 후보를 균일 0.05/0.025/0.0125와 적응형 0.7·0.8·0.85~1.0, 0.00625 미세, NCPU 정렬로 조정.
- `summary.csv`: `-Script` 작업 행의 `config.cfg` 기반 열을 비움.

#### Added
- 주파수별 덤프(`logs/dump_*.csv`: 방사 감쇠, RAO, `B_pto`, 발전 밀도)와 비제어 피크(`B_pto`를 정하는 주파수) 열. 테스트 추가. `src/`는 변경 없음.

### 2026-10-22 — 주파수 격자 검증(grids --quick) 결과 분석
보고서: [docs/reports/2026-10-22_06_freq-grid-quick-study.md](docs/reports/2026-10-22_06_freq-grid-quick-study.md)

#### Verified
- 계산용 PC(Ryzen 7 9700X)에서 `remote.ps1 submit -Script ... --study grids --quick` 실행(8.5분): `-Script` 경로가 실제 SSH에서 동작. 현재 균일 0.05 격자는 201점 기준 대비 총 파워 +3.7%/-1.2%/-3.8%/+11.1%, 개별 WEC 최대 5.9~41.5% 오차. 미세 0.0125 적응형 격자는 총 파워 0.05% 이내이지만 시간이 19~71% 늘어 판정 기준(0.1%/0.3%/+10%)을 동시에 충족하는 후보가 없음. 코드 변경 없음.

### 2026-10-22 — 원격 계산에 -Script 옵션 추가
보고서: [docs/reports/2026-10-22_05_remote-script-option.md](docs/reports/2026-10-22_05_remote-script-option.md)

#### Added
- `scripts/remote.ps1 submit -Script <상대경로.py> -ScriptArgs "<인자>"`: `main.py` 대신 프로젝트 안의 스크립트를 계산용 PC에서 실행(스크립트와 인자는 스냅샷의 `_job.json`으로 전달), `-DryRun`: 계산용 PC에 연결하지 않고 스냅샷만 확인. `summary.csv`에 `script` 칸. 테스트 2건.

#### Changed
- 주파수 격자 설계안(`docs/frequency_grid_design.md`)에 승인된 결정 기록: 새 격자 기본 끔, 상한 자동 확장은 선택 옵션, 판정 기준 0.1%/0.3%/+10%.

### 2026-10-22 — 주파수 격자 설계안과 검증 스크립트
보고서: [docs/reports/2026-10-22_04_frequency-grid-design-and-study.md](docs/reports/2026-10-22_04_frequency-grid-design-and-study.md)

#### Added
- `docs/frequency_grid_design.md`: 주파수 점 수를 NCPU의 배수로 맞추는 옵션(`FreqAlign`)과 공진 인식 격자(`FreqGrid=adaptive`)의 설계안(구현 전, 승인 대기).
- `scripts/experiments/freq_grid_study.py`: 계산용 PC에서 후보 격자·NCPU·메모리 한계를 비교하는 검증 스크립트(`--dry-run`, `--quick`). 테스트 16건. `src/`와 WAMIT 입력은 바뀌지 않음.

### 2026-10-22 — 계산용 PC 원격 실행·결과 자동 회수
보고서: [docs/reports/2026-10-22_03_remote-compute.md](docs/reports/2026-10-22_03_remote-compute.md)

#### Added
- `scripts/remote.ps1`(submit/status/tail/fetch/stop/list)와 `scripts/remote/job_ctl.ps1`: Tailscale + OpenSSH로 계산용 PC에 작업을 보내고 SSH와 분리해 실행, 결과를 `results/<작업ID>/`로 자동 회수.
- `src/utils/run_summary.py`, `scripts/summarize_results.py`: 실행별 `results/summary.csv` 생성. 테스트 3건.
- `docs/remote_compute.md`(설정·사용법), `.gitignore`에 `results/`, `scripts/remote.local.psd1`.

#### Verified
- 실제 두 PC(Tailscale + OpenSSH)에서 짧은 시험 실행으로 보내기→실행→회수→`summary.csv`까지 통과. 설정 중 겪은 문제 해결은 `docs/remote_compute.md`에 정리.

### 2026-10-22 — 쉬운 설명 리포트 폴더(report/) 추가
보고서: [docs/reports/2026-10-22_02_easy-report-folder.md](docs/reports/2026-10-22_02_easy-report-folder.md)

#### Added
- `report/`: 변경 내용을 초등학생도 이해할 수 있게 설명하는 글(처음 글: 처음부터 지금까지의 변경 전체, 이전 대비 새 메쉬 비교 포함)과 목차. `CLAUDE.md` 3-1절에 변경마다 작성하는 규칙 추가.

### 2026-10-22 — MeshPanels 기본값 120으로 상향 및 5기 수렴 결과 정정
보고서: [docs/reports/2026-10-22_01_mesh-panels-default-120.md](docs/reports/2026-10-22_01_mesh-panels-default-120.md)

#### Changed
- `MeshPanels` 기본값 80 → 120. 5기 수렴 테스트(설계 5가지 x 배치 2가지, 개별 WEC 파워 포함)에서 80패널이 총 파워 최대 11%, 개별 WEC 최대 18% 틀려서 상향. 5기 평가 시간 약 6초 → 약 12초. `wec.gdf` 입력이 바뀌므로 이전과 직접 비교 불가.

#### Fixed (documentation)
- 보고서 09, 10, `config.cfg`, README에서 80패널이 5기에서 "총 파워 약 1% 이내, 단조 수렴"이라는 서술을 정정.

### 2026-10-21 — WAMIT 반복 솔버와 주파수 상한 설정
보고서: [docs/reports/2026-10-21_10_wamit-solver-and-omega-max.md](docs/reports/2026-10-21_10_wamit-solver-and-omega-max.md)

#### Added
- `config.cfg`의 `Solver`(WAMIT `ISOLVE`)와 `OmegaMax`(주파수 격자 상한, 기본 3.0). 반복 솔버가 `MAXITT`에 도달한 주파수 경고, 주파수 상한이 응답을 자른 경우의 경고. 테스트 21건.

#### Changed
- 기본 솔버를 직접(`ISOLVE=1`)에서 반복(`ISOLVE=0`)으로 변경. 같은 결과를 5기 전체 405 패널에서 1.45배, 1,025 패널에서 약 2.7배 빠르게 계산.

### 2026-10-21 — 패널 수를 직접 지정하는 개선 메쉬
보고서: [docs/reports/2026-10-21_09_direct-panel-mesh.md](docs/reports/2026-10-21_09_direct-panel-mesh.md)

#### Added
- `config.cfg`의 `MeshPanels`(기당 1/4 모델 목표 패널 수, 도입 당시 기본 80 → 2026-10-22 120으로 상향). `MeshPanels × 기수`가 1,000을 넘으면 메모리 경고. 테스트 16건.

#### Changed
- 원통+반구 메쉬를 큐브드스피어 반구 + 원통 사각형으로 재작성하고 GDF를 직접 씀. 극점 팬이 사라지고 패널이 균일해지며 같은 패널 수에서 1기 오차가 약 절반, 5기 수렴이 단조(R=2.5, D=5.0 한 가지 기준이며 80패널은 일부 형상에서 부정확해 아래 2026-10-22 항목에서 정정). 80패널 기준 5기 평가 32초 → 약 8초.

#### Removed
- `max_elements` 기반 메쉬 크기 계산, 프로파일·회전·gmsh 코드와 `gmsh` 의존성.

### 2026-10-21 — 최소 Python 버전을 3.10으로 상향
보고서: [docs/reports/2026-10-21_08_python-3-10.md](docs/reports/2026-10-21_08_python-3-10.md)

#### Changed
- 최소 지원 Python 3.8 → 3.10. `ruff.toml` target, CI 매트릭스(3.10, 3.12), 문서 표기 갱신. `zip(..., strict=True)` 명시, 3.8용 `from __future__ import annotations` 제거.

### 2026-10-21 — GitHub 공개 준비 보강
보고서: [docs/reports/2026-10-21_07_github-readiness.md](docs/reports/2026-10-21_07_github-readiness.md)

#### Added
- WAMIT 실행 파일 경로 설정: `config.cfg`의 `WAMITPath` 또는 환경 변수 `WAMIT_EXE` (기본값은 기존과 동일). 테스트 4건.
- `CONTRIBUTING.md`, 이슈/PR 템플릿.

#### Changed
- README Prerequisites에 WAMIT 상용 라이선스·Windows 전용 안내 추가.

### 2026-10-21 — 미사용 코드와 빈 폴더 정리
보고서: [docs/reports/2026-10-21_06_cleanup-unused-code.md](docs/reports/2026-10-21_06_cleanup-unused-code.md)

#### Removed
- 호출되지 않던 `calculate_pierson_moskowitz`와 `mesh_axisymmetric_shape.py`의 미사용 생성 함수 8개, 빈 폴더 `.agents/`, `results/`, 이로써 미사용이 된 프로파일 함수 6개, `requirements.txt`의 `matplotlib`.

### 2026-10-21 — CI 워크플로를 python-tests.yml로 통합
보고서: [docs/reports/2026-10-21_05_ci-workflow.md](docs/reports/2026-10-21_05_ci-workflow.md)

#### Changed
- `.github/workflows/python-tests.yml`을 ruff lint 잡과 Python 3.8/3.12 전체 테스트(`unittest discover`) 매트릭스로 확장. 문서의 `ci.yml` 표기를 모두 `python-tests.yml`로 변경.

### 2026-10-21 — RAO 가진력을 diffraction(.3) 기준으로 변경
보고서: [docs/reports/2026-10-21_04_diffraction-excitation.md](docs/reports/2026-10-21_04_diffraction-excitation.md)

#### Changed
- RAO 계산의 파랑 가진력을 Haskind(`wec.2`)에서 diffraction(`wec.3`)으로 변경. `.frc` 출력 옵션 `1 1 0 …` → `1 0 1 …`.
- `calculate_rao_matrix(..., excitation="diffraction"|"haskind")`, `write_frc_file(..., excitation=...)`로 선택 가능 (기본 diffraction).

#### Added
- `tests/test_excitation.py` 5건.

### 2026-10-21 — 변수별 격자 간격, 영일만항 수심 수정, WAMIT 출력 정리
보고서: [docs/reports/2026-10-21_03_step-size-depth-wamit-output.md](docs/reports/2026-10-21_03_step-size-depth-wamit-output.md)

#### Added
- 설계 변수별 격자 간격 `{Var}Step` (`RadiusStep`, `DraftStep`, `WEC1_XStep`, `WEC2_XStep`, `WEC2_YStep`, `WEC3_XStep`, `WEC3_YStep`). 지정하지 않으면 `StepSize` 사용.
- `tests/test_step_size.py` 12건.

#### Fixed
- 영일만항(Yeongilmanhang) 수심 33 m → 13 m.
- 부동소수점 오차로 격자 상한이 탐색에서 빠지던 문제 (예: Y 0.1~30에서 30.0 누락).

#### Changed
- WAMIT `.frc` 출력 옵션 `1 1 1 …` → `1 1 0 …` (미사용 `.3` 출력 생략).

### 2026-10-21 — 설계 변수 양수 규칙 및 GitHub 구조 정비
보고서: [docs/reports/2026-10-21_02_positive-design-variables-and-github.md](docs/reports/2026-10-21_02_positive-design-variables-and-github.md)

#### Added
- `src/utils/validation.py`: 설계 변수 탐색 범위 `0 < Min < Max`, 형상·격자 파라미터 `> 0` 검증 (`ConfigValidationError`).
- `tests/test_validation.py`: 양수 규칙 테스트 10건.
- GitHub 구성: `.gitignore`, `.gitattributes`, `requirements-dev.txt`, `.github/workflows/python-tests.yml`, `CHANGELOG.md`, `CLAUDE.md`, `docs/reports/`.

#### Changed
- `config.cfg`: `WEC2_YMin`, `WEC3_YMin`을 0에서 0.1로 변경. 설계 변수 주석을 `[Float > 0]`로 표기.
- `get_layout_config`: Y 범위 키가 필수가 됨(기본값 0.0 제거). `NumWECs`는 1/3/5만 허용.
- `write_wamit_inputs`: 반지름·흘수가 양수가 아니면 거부.
- 문서: README, conventions(y_i > 0), architecture, algorithms_and_problems 갱신.

### 2026-10-21 — 버그·위험 항목 수정 및 ruff 도입
보고서: [docs/reports/2026-10-21_01_bugfix-and-ruff.md](docs/reports/2026-10-21_01_bugfix-and-ruff.md)

#### Fixed
- config 파서가 음수 값이 있는 줄을 무시하던 문제 (`src/utils/config_parser.py`).
- 로그가 재실행 시 덮어써지고 DE 로그에만 알고리즘 이름이 없던 문제.
- `main.py`가 최적해를 출력하지 않던 문제.
- PSO와 CMA-ES에서 대칭 정렬이 알고리즘 내부 상태를 뒤섞던 문제.
- 패널티 평가가 WAMIT 실행 수에 섞여 집계되던 문제.
- WAMIT 실패 시 원인 메시지가 숨겨지던 문제. 이전 실행의 출력과 에러 로그를 실행 전에 삭제.
- mesh 모듈이 Python 3.8에서 import되지 않던 문제.

#### Added
- 실행별 `*_config.json`, `*_summary.json` 로그 (중단 시에도 기록).
- `tests/test_fixes.py` 회귀 테스트 14건, `ruff.toml`.

#### Changed
- 전체 코드에 `ruff check` 및 `ruff format` 적용.
