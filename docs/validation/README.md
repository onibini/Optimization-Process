# 검증 기준 결과 (논문 최적해 재현)

프로세스(주파수 격자, 메쉬, 스펙트럼, 물리 코드, 환경 파일 등)를 바꾼 뒤 결과가 바뀌었는지 확인하기 위한 기준 자료입니다.

- 기준 파일: [paper_check_reference.csv](paper_check_reference.csv) (144행; 계산용 PC, 2026-10-23)
- 만든 도구: `scripts/experiments/paper_check.py`
- 코드 상태: 커밋 `ee65e22` (FreqGrid 추가 직후; `FreqGrid=0`, 즉 균일 0.05 rad/s 51점) + `paper_check.py`
- 설정: 5 WEC, 수직벽(IWALLX0=1), `Solver=0`(반복), `OmegaMax=3.0`, `MeshPanels` 120과 200, JONSWAP γ=1.4, WAMIT v7 32-bit
- 평가 시간: 메쉬 120 약 8 s, 200 약 21 s (설계 1개, NCPU=8)

## 1. 무엇이 들어 있나

논문(동시 최적화 논문 ver14) Table 4의 최적해 6개(부안·칠발도·영일만항 × 순차·동시)를 **최적화 없이** `evaluate_joint`와 같은 경로로 계산한 총 발전량입니다. 설계 변수는 논문 `(x1, y1, x2, y2, x3, r, d)`를 프로젝트 벡터 `[R, D, X1, X2, Y2, X3, Y3] = [r, d, x3, x2, y2, x1, y1]`로 바꿔 넣습니다(논문은 WEC3, 프로젝트는 WEC1이 중심선).

CSV의 각 행은 한 번의 WAMIT 결과를 다음 조합으로 해석한 값입니다: 가진력(`diffraction`=현재 기본 `wec.3`, `haskind`=`wec.2`) × 스펙트럼(`goda`=현재 기본 WaveSpec 2, `ittc`=WaveSpec 1) × 적분(`simpson`=현재, `trapz`, `rect`) × 메쉬(120, 200).

## 2. 논문과의 비교 (diffraction, Simpson)

| 해역 | 방식 | 수심 m | 논문 kW | 메쉬 120 ITTC | 메쉬 200 ITTC | 메쉬 120 Goda |
| --- | --- | --- | --- | --- | --- | --- |
| Buan | sequential | 50 | 47.52 | 47.15 (-0.8%) | 47.23 (-0.6%) | 51.29 (+7.9%) |
| Buan | simultaneous | 50 | 50.36 | 50.02 (-0.7%) | 50.13 (-0.4%) | 54.41 (+8.0%) |
| Chilbaldo | sequential | 33 | 31.33 | 31.01 (-1.0%) | 30.76 (-1.8%) | 33.73 (+7.7%) |
| Chilbaldo | simultaneous | 33 | 31.91 | 31.69 (-0.7%) | 31.72 (-0.6%) | 34.47 (+8.0%) |
| Yeongilmanhang | sequential | 13 | 29.23 | 35.49 (+21.4%) | 35.61 (+21.8%) | 38.61 (+32.1%) |
| Yeongilmanhang | simultaneous | 13 | 29.32 | 35.83 (+22.2%) | 35.94 (+22.6%) | 38.98 (+32.9%) |

- **Goda(2026-10-23까지 기본값, 지금은 ITTC가 기본)는 논문보다 약 8% 높다**: 코드의 Goda 식은 적분하면 입력 Hs를 약 4.1% 크게 준다(ITTC는 0.15% 이내). 논문 숫자는 ITTC와 맞는다.
- **부안·칠발도는 ITTC로 -0.2~-1.8%에서 논문과 일치** → 이 평가 과정의 정확도는 논문 수준이다.
- **영일만항은 실제 수심 13 m가 정답**이고(사용자 확인, 2026-10-23), 현재 `env_data.csv`도 13 m다. 논문의 영일만항 수치(29.23, 29.32 kW)는 환경 파일의 잘못된 수심(33 m)으로 계산된 것으로 보여 이 해역의 논문 대비 +21%(ITTC)는 비교 대상이 아니라 논문 쪽 값의 문제다. 이 해역의 기준값은 논문이 아니라 13 m로 계산한 현재 결과다(33 m 결과는 기준에서 뺐다).
- 자세한 분석: `docs/reports/2026-10-23_06_paper-check-result.md`.

## 3. 파일을 바꾼 뒤 확인하는 법

계산용 PC에서 실행(WAMIT 필요, 약 10분):

```powershell
.\scripts\remote.ps1 submit -Name paper_check -Script scripts/experiments/paper_check.py -ScriptArgs "--reference docs/validation/paper_check_reference.csv" -Wait
```

`--reference`는 같은 조합(해역·방식·메쉬·수심·가진력·스펙트럼·적분)의 총 발전량을 저장된 기준과 비교해 **0.2%**(`--tolerance`)보다 크게 달라진 조합을 출력하고 종료 코드 1을 돌려줍니다.

| 바꾼 것 | 기대 |
| --- | --- |
| 리팩터링(물리·WAMIT 입력 불변) | 모든 조합이 일치(0.0%) |
| `FreqGrid=1` 적용 | 일치해야 하는 것은 아니며, 차이가 0.1~0.3% 이내인지 본다(기준은 균일 0.05) |
| `WaveSpec`, Goda 식 수정 | goda 행만 달라진다. ITTC 행은 그대로여야 한다 |
| `env_data.csv` 수심 수정 | 해당 해역의 행만 달라진다 |
| 메쉬(`MeshPanels`) 변경 | 120/200 이외 값은 기준에 없으므로 비교되지 않는다(필요하면 기준을 새로 만든다) |

`--meshes`, `--sites`로 일부만 돌려도 기준과 겹치는 조합만 비교합니다(겹치는 것이 없으면 실패). 기준을 바꿀 때는 새 결과 CSV를 이 폴더에 복사하고 이 문서의 코드 상태·표를 함께 고칩니다.

## 4. 한계

- 논문 당시 코드의 메쉬·가진력 정확한 설정은 알 수 없어 ITTC 일치 후에도 -0.2~-1.8%가 남는다(원인 미확정).
- 기준은 `FreqGrid=0`(균일 0.05) 값이다. 균일 0.05는 좁은 공진 형상에서 오차가 큰 것으로 알려져 있어(`docs/frequency_grid_design.md`), 이 6개 설계에서는 그 영향이 -1% 이내로 나타났다.
- 이 기준은 5 WEC, R=2.5, 수직벽 설계 6개에만 해당한다.
