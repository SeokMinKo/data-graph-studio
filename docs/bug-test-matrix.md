# DGS Bug Type → Test Coverage Matrix

이 문서는 DGS의 버그 유형을 기준으로 현재 테스트 커버리지와 추가 강화 포인트를 매핑한다.

## 1) 기능 누락형 (Function Missing / Wrong Dispatch)
- 대표 리스크
  - 수식 함수 미구현 또는 잘못된 함수 라우팅
- 현재 테스트
  - `tests/test_bug_fixes.py`
    - `test_sin_function`
    - `test_cos_function`
    - `test_tan_function`
    - `test_contains_function`
    - `test_substring_function`
- 이번 추가
  - `test_contains_handles_none_values_without_crash`
  - `test_substring_overflow_length_is_safe`

## 2) 경계값/엣지 케이스형 (Boundary / Empty / Zero)
- 대표 리스크
  - 빈 데이터, 0 파라미터, 과대 길이 입력에서 크래시
- 현재 테스트
  - `tests/test_bug_fixes.py`
    - `TestSamplingEdgeCases` (empty/zero)
    - `TestTrellisEdgeCases` (panels_per_page=0)

## 3) 상태 동기화/참조 공유형 (State Sync / Deep Copy)
- 대표 리스크
  - state 간 shallow copy로 인한 사이드이펙트
- 현재 테스트
  - `tests/test_bug_fixes.py`
    - `TestStateDeepCopy`

## 4) 프로젝트 저장/복원형 (Project Save/Restore)
- 대표 리스크
  - 저장 필드 누락, 로드시 레거시 호환 실패, 경로 해석 실패
- 현재 테스트
  - `tests/test_project.py`
    - 직렬화/파일 I/O/검증/autosave 기본 시나리오
- 이번 추가
  - `test_legacy_data_source_migrates_to_data_sources`
  - `test_profiles_round_trip_is_preserved`
  - `test_validate_resolves_relative_path_against_project_location`
  - `test_validate_includes_named_data_source_in_error_message`

## 5) 파서/컨버터 파이프라인형 (Parser/Converter Pipeline)
- 대표 리스크
  - converter 이름 오타/미지원 값 처리 실패
  - CPU별 스케줄 runtime 계산 오염
- 현재 테스트
  - `tests/unit/test_ftrace_parser.py`
  - `tests/unit/test_blocklayer_converter.py`
- 이번 추가
  - `tests/test_bug_fixes.py`
    - `test_unknown_converter_raises_clear_error`
    - `test_sched_converter_runtime_is_per_cpu`

## 6) UI 이벤트/상호작용형 (Selection/Draw/Event)
- 대표 리스크
  - mouse press/move/release 순서 처리 불량
  - selection/drawing 상태 꼬임
- 현재 테스트
  - `tests/unit/test_selection_sync.py`
  - `tests/unit/test_mini_graph_widget.py`
  - `tests/test_drawing.py`
  - `tests/test_integration.py`
- 권장 추가(다음 배치)
  - 툴 모드 전환 중 drag 시작/종료 이벤트 순서 회귀 테스트
  - selection ROI 생성 후 즉시 clear 시 상태 정합성 테스트

## 7) 플랫폼/운영환경형 (Permission/Path/Runtime)
- 대표 리스크
  - Windows 권한/경로, Perfetto 권한/실행 방식
- 현재 테스트
  - `tests/unit/test_perfetto_oneshot_fallback.py`
  - `tests/test_updater_validation.py`

---

## 우선순위 제안 (테스트 투자 대비 효과)
1. 프로젝트 복원/호환성 회귀 (데이터 손실 리스크 큼)
2. 파서/컨버터 입력 변형 및 에러 메시지 고정
3. UI 이벤트 시퀀스 회귀 (사용자 체감 버그)
4. 대용량 데이터 성능/시간 제한 스모크

## 운영 규칙
- 새 버그 수정 시 반드시 "재현 테스트 1개 + 인접 회귀 1개"를 함께 추가한다.
- CHANGELOG의 bugfix 항목은 가능한 한 테스트 함수 이름으로 역추적 가능하게 유지한다.
