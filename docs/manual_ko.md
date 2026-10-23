# 사용 설명서

이 문서는 WEC(파력발전기) 배열의 형상·배치 최적화 프로그램을 설치하고, 설정하고, 실행하고, 결과를 읽는 방법을 설명합니다. 프로젝트 소개는 [README](../README.md)에 있습니다.

## 목차

1. [프로그램 개요](#1-프로그램-개요)
2. [설치](#2-설치)
3. [빠른 시작](#3-빠른-시작)
4. [설정 파일 config.cfg](#4-설정-파일-configcfg)
5. [해역 데이터 env_data.csv](#5-해역-데이터-env_datacsv)
6. [실행 중 화면 읽기](#6-실행-중-화면-읽기)
7. [결과 파일](#7-결과-파일)
8. [계산용 PC에서 원격 실행](#8-계산용-pc에서-원격-실행)
9. [실험·검증 스크립트](#9-실험검증-스크립트)
10. [권장 설정과 팁](#10-권장-설정과-팁)
11. [문제 해결](#11-문제-해결)
12. [자주 묻는 질문](#12-자주-묻는-질문)

명령 예시는 Windows **cmd(명령 프롬프트)** 기준입니다. 먼저 프로젝트 폴더로 이동하세요.

```cmd
cd /d "C:\경로\Optimization-Process"
```

---

## 1. 프로그램 개요

![개요](images/overview.png)

- **대상**: 수직벽(방파제) 앞에 놓인 heave(상하 운동) point-absorber WEC 1·3·5기. 형상은 원통 + 반구 바닥이며, 반지름 *R*과 원통부 길이 *D*로 정합니다(총 흘수 = *D* + *R*).
- **목표**: 대상 해역의 불규칙파에서 배열 전체의 시간 평균 발전량(W)을 최대화합니다.
- **해석**: WAMIT v7으로 부가질량·방사감쇠·가진력을 계산합니다(수직벽 반사 포함). 모든 WEC의 heave 운동을 연성해 RAO를 구하고, PTO 감쇠는 각 WEC의 비제어 공진 주파수에서의 방사감쇠로 정합니다. 발전량은 스펙트럼과 곱해 Simpson 적분합니다.
- **최적화 모드**: 1 형상(1기), 2 배치(형상 고정), 3 형상 + 배치 동시.
- **설계 변수**: `[R, D, X1, X2, Y2, X3, Y3]`(5기, 동시 최적화). WEC1은 중심선(y = 0) 위에 있고, WEC2와 WEC3은 y = 0에 대해 대칭인 쌍입니다. 모든 변수는 0.1 m 격자 위에서 움직이고, 양수만 허용합니다.
- **알고리즘**: DE(기본), PSO, GA, CMA-ES, DEPSO.

> 논문(Lee 등, 2026)의 WEC 번호는 중심선 위가 WEC3입니다. 이 프로그램은 중심선 위가 WEC1입니다. 논문 값 (x1, y1, x2, y2, x3, r, d)는 `[r, d, x3, x2, y2, x1, y1]`로 넣습니다.

## 2. 설치

1. **Python 3.10 이상**을 설치합니다(3.11 권장).
2. 의존성을 설치합니다.

   ```cmd
   pip install -r requirements.txt
   ```

3. **WAMIT v7(32-bit)**: 상용 프로그램이라 포함되어 있지 않습니다. 라이선스가 있는 Windows PC에 설치합니다. 실행 파일은 다음 순서로 찾습니다.
   1. `config.cfg`의 `WAMITPath` (경로에 공백이 없어야 함)
   2. 환경 변수 `WAMIT_EXE`
   3. `C:\WAMITv7\WAMIT.exe`
4. WAMIT 없이도 테스트는 돌아갑니다.

   ```cmd
   python -m unittest discover -s tests
   ```

## 3. 빠른 시작

1. `config.cfg`에서 모드·알고리즘·해역을 고릅니다. 예: 영일만항(`SiteID 3`)에서 5기 형상·배치 동시 최적화를 DE로 할 때는 다음과 같습니다.

   ```
   3     OptMode
   1     Algorithm
   5     NumWECs
   3     SiteID
   ```

2. 실행합니다.

   ```cmd
   python main.py
   ```

   다른 설정 파일을 쓰려면 `python -c "import main; main.main('my.cfg')"`처럼 실행합니다.

3. 끝나면 최적 설계(발전량, R, D, 총 흘수, 각 WEC 좌표)가 화면에 나오고, `logs\`에 기록이 남습니다.

## 4. 설정 파일 config.cfg

한 줄은 `값  이름  - 설명` 형식입니다. `#`로 시작하는 줄은 주석입니다. 값에는 공백이 없어야 합니다.

### 4-1. [Simulation]

| 키 | 값 | 설명 |
| --- | --- | --- |
| `OptMode` | 1, 2, 3 | 1 형상(1기, 개방 해역), 2 배치(`FixedRadius`, `FixedDraft` 고정), 3 형상 + 배치 |
| `Algorithm` | 1~5 | 1 DE, 2 PSO, 3 GA, 4 CMA-ES, 5 DEPSO |
| `WaveSpec` | 1~3 | 1 JONSWAP ITTC(**기본**), 2 JONSWAP Goda(Hs가 약 4% 크게 나와 비교용), 3 Pierson-Moskowitz |

### 4-2. [WEC Parameters]

| 키 | 설명 |
| --- | --- |
| `NumWECs` | 1, 3, 5 |
| `MinSpacing` | WEC 중심 사이 최소 거리 = `MinSpacing` × R. 어기면 WAMIT 없이 벌점(패널티)을 받습니다. |
| `FixedRadius`, `FixedDraft` | 배치 최적화(`OptMode 2`)의 고정 형상 |

수직벽은 모드 2, 3에서 자동으로 켜집니다. WEC와 벽 사이 간격은 x 하한(`WECn_XMin`)으로 정합니다. 예: x ≥ 3.0 m이면 R = 2.5 m에서 0.5 m입니다.

### 4-3. [AlgorithmSettings]

| 키 | 쓰는 알고리즘 | 설명 (기본) |
| --- | --- | --- |
| `PopSize` | 전체 | 개체(입자) 수. 논문 DE는 100, CMA-ES는 72 권장 |
| `MaxIter` | 전체 | 세대 수. 조기 종료는 없습니다. |
| `F`, `CR` | DE, DEPSO | 변이 가중치(0.5), 교차 확률(0.9) |
| `DEUpdate` | DE | 0 즉시 교체(기본, 논문), 1 세대 단위(`Workers`로 병렬 가능, 같은 품질에 약 1.15배 세대 필요) |
| `w`, `c1`, `c2` | PSO, DEPSO | 관성(0.5), 개인 최고 쪽(1.5), 전체 최고 쪽(1.5) |
| `MutationRate` | GA | 자식마다 돌연변이가 일어날 확률(0.1) |
| `SigmaInit` | CMA-ES | 처음 탐색 폭(범위 대비 비율, 0 초과 1 이하, 0.3) |

### 4-4. [Constraints]

| 키 | 설명 |
| --- | --- |
| `StepSize` | 모든 변수의 격자 간격(0.1 m). 변수별로 바꾸려면 `RadiusStep`, `WEC2_YStep` 같은 줄의 `#`을 지웁니다. |
| `RadiusMin/Max`, `DraftMin/Max` | 형상 범위(기본 R 0.5~2.5, D 0.5~5.0) |
| `WEC1_XMin/Max` … `WEC3_YMin/Max` | 배치 범위(기본 x 3~25, y 0.1~30) |

모든 범위는 **0 < Min < Max**여야 합니다. 어기면 시작할 때 어떤 변수가 틀렸는지 알려 주고 멈춥니다.

### 4-5. [Environment]

| 키 | 설명 |
| --- | --- |
| `SiteID` | `data/env_data.csv`의 행 번호(1 부안, 2 칠발도, 3 영일만항) |

### 4-6. [WAMIT Settings]

| 키 | 기본 | 설명 |
| --- | --- | --- |
| `NCPU` | 8 | WAMIT 하나가 쓰는 코어 수 |
| `RAMGBMAX` | 16 | WAMIT 메모리 한도(GB) |
| `WAMITPath` | (없음) | WAMIT 실행 파일 경로(선택) |
| `MeshPanels` | 120 | 1기당 1/4 모델 패널 수. 5기에서 대부분 총 발전량 0.5% 이내이고, 평가 1회에 약 8~12초 걸립니다. 가늘고 긴 형상은 160 이상, 1기는 150~250을 권장합니다. |
| `Solver` | 0 | 0 반복 솔버(빠름), 1 직접 솔버. 반복 솔버가 수렴하지 못하면 경고가 나옵니다. |
| `OmegaMax` | 3.0 | 주파수 상한(rad/s). 작은 부표는 고주파에서 공진하므로 3.0을 유지하세요. |
| `FreqGrid` | 0 | 0 균일 0.05 격자(51점), 1 공진 부근만 촘촘한 적응형 격자. 1은 정확하지만(오차 0.1% 이내) 시간이 1.5~2.5배 걸립니다. |
| `Workers` | 1 | 동시에 돌리는 WAMIT 수. `Workers × NCPU` ≤ 코어 수로 맞춥니다(예: 2 × 4). GA, CMA-ES, `DEUpdate=1`인 DE는 세대 전체를 병렬로 평가합니다. |

32-bit WAMIT은 `MeshPanels × NumWECs`가 약 1,100~1,300을 넘으면 메모리 오류가 납니다. NCPU가 작을수록 여유가 생깁니다.

## 5. 해역 데이터 env_data.csv

```
SiteID,SiteName,Hs,Tp,Gamma,Depth
1,Buan,1.07,5.46,1.4,50
2,Chilbaldo,0.87,4.48,1.4,33
3,Yeongilmanhang,0.92,6.66,1.4,13
```

- `Hs` 유의파고(m), `Tp` 첨두주기(s), `Gamma` JONSWAP 첨두증폭계수, `Depth` 수심(m).
- 새 해역은 행을 추가하고 `SiteID`로 고릅니다.

## 6. 실행 중 화면 읽기

```
WAMIT: Solver=0, 51 frequencies up to 3 rad/s, MeshPanels=120
Algorithm: [Differential Evolution]
 Gen 12 | Best: 48.1234 kW | Hits: 35 | WAMIT: 1180 | Penalty: 210
```

| 항목 | 뜻 |
| --- | --- |
| `Best` | 지금까지 가장 좋은 배열 발전량 |
| `Hits` | 이미 계산한 설계라 캐시에서 가져온 횟수(WAMIT 안 돌림) |
| `WAMIT` | 실제 WAMIT 실행 횟수 |
| `Penalty` | 간격 제약을 어겨 WAMIT 없이 버린 설계 수 |

나올 수 있는 경고는 다음과 같습니다.
- `reached MAXITT`: 반복 솔버가 일부 주파수에서 수렴하지 못했습니다. 자주 나오면 `Solver=1`로 바꾸세요.
- `Power density is not negligible at the highest WAMIT frequency`: 공진이 `OmegaMax` 위에 있습니다(작은 부표).
- `exceeds ... panels`: 패널 수가 32-bit 메모리 한계에 가깝습니다.

## 7. 결과 파일

실행마다 `logs\{해역}_{알고리즘}_{날짜_시각}_*` 파일 네 개가 생깁니다(서로 덮어쓰지 않음).

| 파일 | 내용 |
| --- | --- |
| `*_config.json` | 실행에 쓴 설정(범위, 환경, WAMIT 설정) |
| `*_trial_history.csv` | 평가한 모든 고유 설계와 발전량(WEC별 포함), `penalized` = 1이면 제약 위반 |
| `*_generation_history.csv` | 세대별 최고 설계·발전량·소요 시간 |
| `*_summary.json` | 최종 최적 설계, 세대 수, WAMIT·캐시·패널티 횟수(중간에 멈춰도 기록) |

수렴 곡선은 `generation_history.csv`의 `fitness`(W)를 세대(`iter`)에 대해 그리면 됩니다.

## 8. 계산용 PC에서 원격 실행

WAMIT이 설치된 계산용 PC에 SSH(Tailscale)로 작업을 보내고 결과를 가져옵니다. 처음 한 번의 설정은 [remote_compute.md](remote_compute.md)를 보세요.

보내고 끝날 때까지 기다린 뒤 결과를 가져옵니다.

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote.ps1 submit -Name site3 -Wait
```

진행 상황을 봅니다(마지막 줄들).

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote.ps1 tail -JobId <작업ID>
```

결과를 가져옵니다(`results\<작업ID>\`).

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote.ps1 fetch -JobId <작업ID>
```

여러 해역을 한 작업에서 차례로 돌립니다.

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remote.ps1 submit -Config my.cfg -Name sites -Script scripts/experiments/run_sites.py -ScriptArgs "--sites 1 2 3"
```

실시간으로 보려면 계산용 PC의 로그를 따라 읽습니다.

```cmd
ssh wec-compute "powershell -NoProfile -Command Get-Content C:\wec_jobs\<작업ID>\run.log -Encoding UTF8 -Wait -Tail 30"
```

## 9. 실험·검증 스크립트

`scripts\experiments\`에 있습니다. WAMIT이 필요한 것은 계산용 PC에서 `remote.ps1 submit -Script ...`로 돌립니다.

| 스크립트 | WAMIT | 용도 |
| --- | --- | --- |
| `paper_check.py` | 필요 | 논문 최적해를 다시 계산해 발전량을 비교합니다. `--reference docs/validation/paper_check_reference.csv`를 붙이면 코드를 바꾼 뒤 결과가 변했는지 확인합니다(0.2% 이상 변하면 실패). |
| `freq_grid_study.py` | 필요 | 주파수 격자 후보의 정확도·시간 비교 |
| `parallel_wamit_bench.py` | 필요 | `Workers × NCPU` 조합별 처리 속도 측정 |
| `run_sites.py` | 필요 | 같은 설정으로 여러 해역을 차례로 실행 |
| `algorithm_benchmark.py` | 불필요 | 최적화 알고리즘을 벤치마크 함수로 비교(`--rotate`, `--grid 0`, `--plot`) |
| `de_update_benchmark.py` | 불필요 | DE 즉시 교체와 세대 단위 교체 비교 |

## 10. 권장 설정과 팁

- **논문과 비교하려면**: `WaveSpec=1`(ITTC), `MeshPanels=120`, `FreqGrid=0`, DE `PopSize 100`, `MaxIter 300`, `F 0.5`, `CR 0.9`로 둡니다.
- **정확도 우선**: `FreqGrid=1`을 쓰고, 가늘고 긴 형상이 범위에 있으면 `MeshPanels` 160 이상으로 올립니다.
- **속도 우선**: `Workers`(예: 2 × NCPU 4)를 쓰고, GA·CMA-ES 또는 `DEUpdate=1`인 DE를 고릅니다. 실제 속도는 `parallel_wamit_bench.py`로 먼저 확인하세요.
- **알고리즘 선택**: 벤치마크에서는 7개 변수에서 DE와 CMA-ES(개체 72)가 비슷했고, 변수가 많고 다봉일수록 CMA-ES가 나았습니다. CMA-ES는 개체 수가 작으면(9) 국소해에 갇히므로 50~100을 권장합니다.
- **설정을 바꾼 뒤**: `paper_check.py --reference ...`로 결과가 변하지 않았는지 확인합니다([docs/validation](validation/README.md)).

## 11. 문제 해결

| 증상 | 원인과 해결 |
| --- | --- |
| `WAMIT executable not found` | `WAMITPath`나 `WAMIT_EXE`를 확인합니다(공백 없는 경로). |
| `WamitRunError` (메모리 할당 오류) | 패널이 너무 많습니다. `MeshPanels`를 줄이거나 `NCPU`를 줄입니다. |
| WAMIT이 출력 없이 끝남 | 작업 폴더 경로가 너무 깁니다. 짧은 경로에서 실행합니다. |
| `ConfigValidationError` | 범위가 0 < Min < Max가 아니거나 간격이 0 이하입니다. 메시지에 나온 변수를 고칩니다. |
| `WaveSpec must be one of ...` | `WaveSpec`은 1, 2, 3 중 하나여야 합니다. |
| 발전량이 예전보다 약 8% 낮음 | 2026-10-23부터 기본 스펙트럼이 Goda에서 ITTC로 바뀌었습니다(ITTC가 입력 Hs와 맞음). |
| 원격 로그의 한글이 깨짐 | `Get-Content ... -Encoding UTF8`로 읽습니다. |

## 12. 자주 묻는 질문

**Q. WAMIT 없이 무엇을 할 수 있나요?**
테스트, 알고리즘 벤치마크, 설정 검증, 코드 수정을 할 수 있습니다. 발전량 계산은 WAMIT이 필요합니다.

**Q. 같은 설계를 두 번 계산하나요?**
아니요. 격자 위의 같은 점(대칭으로 같은 배치 포함)은 캐시에서 가져옵니다.

**Q. 계산 시간은 얼마나 걸리나요?**
5기, 패널 120, 51 주파수에서 평가 1회에 약 8초입니다. 개체 100 × 300세대 DE는 캐시를 고려해도 해역당 수십 시간 걸릴 수 있습니다. `Workers`와 `FreqGrid`의 영향은 위 표를 보세요.

**Q. 결과를 인용하려면?**
[README의 Citation](../README.md#citation)을 보세요.
