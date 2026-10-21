# 업데이트 보고서: 미사용 코드와 빈 폴더 정리

- 날짜: 2026-10-21
- 범위: `src/physics/mesh_axisymmetric_shape.py`, `src/physics/wave_spectrum.py`

## 1. 개요

호출되지 않는 함수와 빈 폴더, 캐시를 정리했습니다. 동작 변경은 없습니다.

## 2. 삭제한 코드

- `wave_spectrum.py`: `calculate_pierson_moskowitz` (`WaveSpec`은 1=ITTC, 2=Goda만 지원하며 호출처 없음).
- `mesh_axisymmetric_shape.py`: `generate_cone_mesh`, `generate_hemisphere_mesh`, `generate_cylinder_mesh`, `generate_cylinder_cone_mesh`, `generate_cylinder_bspline_mesh`, `generate_bspline1_mesh`, `get_flat_circle_profile`, `visualize_profile` (약 237줄). 사용 중인 형상은 `generate_cylinder_hemisphere_mesh`뿐입니다.

## 3. 정리한 폴더

- 빈 폴더 `.agents/`, `results/` 삭제. `__pycache__/`, `.ruff_cache/` 삭제(재생성됨). `logs/`의 기존 로그는 그대로 둡니다.

## 4. 후속 정리

- 삭제한 생성 함수만 호출하던 프로파일 함수 6개(`get_cone_profile`, `get_hemisphere_profile_advanced`, `get_cylinder_profile`, `get_cylinder_cone_profile`, `get_cylinder_bspline_profile`, `get_bspline1_profile`)를 삭제했습니다.
- `visualize_profile` 삭제로 코드에서 쓰이지 않게 된 `matplotlib`을 `requirements.txt`와 `docs/architecture.md`에서 제거했습니다.

## 5. 남은 후보

프로파일 함수 삭제로 새로 호출처가 없어진 헬퍼: `get_line_points`, `get_bspline_points`, `_get_distribution_t`, `alloc_elem_num`, `calc_polyline_length` (`de_boor`, `dist`도 이들만 쓸 수 있음). 이번에는 삭제하지 않았습니다.

## 6. 검증

py311에서 `ruff check .`, `ruff format --check .`, 단위 테스트 55건(skip 3) 통과.
