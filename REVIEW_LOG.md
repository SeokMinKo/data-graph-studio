# PRD Review Log

## Round 1
Date: 2026-02-02 21:55 KST

### 🧠 Behavior Reviewer
**Status**: ❌ REJECT

**주요 피드백**:
1. Dataset vs Project 용어 모호
2. Active project 정의 없음 (무엇이 활성화?)
3. Selection model 없음 (단일/다중 선택, 키보드 네비게이션)
4. Profile apply 시 unsaved changes 덮어쓰기 경고 없음
5. Name validation 규칙 없음 (빈 이름, 중복, 최대 길이)
6. Delete 후 active profile 처리 미정의
7. Duplicate 대상/네이밍 규칙 없음
8. Export/Import 대상(단일/다중) 불명확
9. Toolbar Save/Load vs Export/Import 구분 불명확
10. Error handling 전무
11. 키보드 접근성 없음
12. Undo/Redo 정책 없음

### 🏗️ Structure Reviewer
**Status**: ❌ REJECT

**주요 피드백**:
1. DatasetState에 profiles 추가 → 상태 객체 비대화
2. GraphSetting의 Dict/List[Dict] → 타입 불명확
3. DatasetState ↔ GraphSetting 매핑 계약 없음
4. AppState가 CRUD까지 담당 → God object 경향
5. 런타임 모델 = 직렬화 포맷 → 유연성 저하
6. 버전/마이그레이션 전략 없음
7. QTreeWidget은 모델-뷰 분리 불리
8. ID 중복/생성 규칙 없음
9. 이름 충돌 정책 없음
10. Timestamp 업데이트 규칙 없음

### 🎨 UI Reviewer
**Status**: ❌ REJECT

**주요 피드백**:
1. 📁 아이콘이 파일명과 불일치 (폴더 아이콘 + 파일명)
2. 한/영 혼용 UI
3. "+ 새 프로파일"이 트리 아이템처럼 보임 → 액션과 구분 필요
4. 이모지 아이콘 OS별 렌더링 차이
5. 상태 정의 부족 (focused, disabled, loading 등)
6. Single click = apply → 실수 위험
7. 클릭 영역 명확화 필요 (아이콘 vs 라벨)
8. Active project vs Selected profile 시각적 구분 없음
9. 키보드 접근성 없음
10. 긴 이름 처리 없음 (ellipsis/tooltip)
11. 빈/에러 상태 UI 없음
12. WCAG 색상 대비 규정 없음

### 🔍 Overall Reviewer
**Status**: ❌ REJECT

**주요 피드백**:
1. 목표 모호 (어떤 IDE 패턴?)
2. 성공 기준 측정 불가
3. 데이터 모델 관계 정의 없음
4. CRUD edge cases 미정의
5. 파일 포맷 버저닝 없음
6. Import 충돌 처리 없음
7. 마이그레이션 계획 없음
8. 테스트 시나리오 부실
9. 접근성/성능 요구사항 없음
10. 용어/로컬라이제이션 정책 없음

### ⚡ Algorithm Reviewer
**Status**: ❌ REJECT

**주요 피드백**:
1. _update_tree()가 O(N) 전체 재구성 → 비효율
2. QTreeWidget은 진정한 가상화 아님
3. Signal cascade → 다중 UI 업데이트
4. 재진입 방지 없음
5. 직렬화 포맷 버전 없음
6. Deep copy 필요 → 메모리/성능 문제
7. 대용량 nested data 처리 미정의
8. 메모리 중복 (3중 복사 가능성)
9. 비동기 I/O 처리 없음
10. NFR 테스트 기준 모호

---

## Actions for Round 2
PRD 전면 수정 필요:
1. 용어 정의 명확화 (Dataset=Project)
2. 모든 상태/인터랙션 정의
3. 에러 핸들링 추가
4. 이름 충돌/validation 규칙
5. 키보드 접근성
6. 아키텍처 개선 (ProfileManager 분리)
7. 성능 최적화 전략 (incremental update)
8. 버저닝/마이그레이션
9. 측정 가능한 성공 기준
