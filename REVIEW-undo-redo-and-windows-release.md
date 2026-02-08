# 12인 리뷰 (라이트) — Undo/Redo 확대 + Windows 설치형 배포/자동 업데이트

Date: 2026-02-09

> NOTE: 원래 너 시스템의 “12인 리뷰” 포맷을 완전 자동화한 건 아니고,
> 이번에는 빠르게 위험 포인트를 훑는 **라이트 버전 체크리스트**로 기록한다.

## 1. Behavior Reviewer
- [AGREE] Undo/Redo가 실제로 상태를 적용하는지(기존 pop-only 문제 해결)
- [AGREE] 세션 한정이라는 스코프가 명확함
- [CONCERN] Dataset remove undo는 대형 DF에서 메모리 부담 가능

## 2. Structure Reviewer
- [AGREE] Undo core를 core(undo_manager)로 분리
- [AGREE] state 변경은 record, UI mutation은 push/record 분리하는 방향이 합리적
- [RESOLVED] UndoAction 호환 레이어 제거 완료(UndoCommand로 통일)

## 3. UI Reviewer
- [AGREE] History Panel이 dock + View 메뉴 토글 제공
- [CONCERN] 타임라인에서 항목 클릭으로 특정 시점으로 jump(다단 undo) 기능은 없음(향후)

## 4. Algorithm Reviewer
- [AGREE] 스냅샷 기반(필터/정렬/차트) + 커맨드 기반 혼합이 구현 난이도 대비 안전
- [CONCERN] deepcopy 비용(필터 리스트는 OK, chart settings OK)

## 5. Reliability Reviewer
- [AGREE] pause 가드로 재진입/루프 위험 완화
- [CONCERN] AnnotationController는 전체 snapshot 복원 방식이라 annotation 수가 매우 많으면 부담

## 6. Security Reviewer
- [AGREE] 업데이트는 GitHub Release asset 다운로드/실행으로 단순
- [CONCERN] 서명/무결성 검증은 없음(설치형 배포라 현실적으로 필요할 수 있음)

## 7. Release/DevOps Reviewer
- [AGREE] 태그 푸시 트리거로 installer 생성/업로드
- [CONCERN] CI에서 PyInstaller 빌드 시간이 길어질 수 있음, 캐시 전략 고려

## 8. Testing Reviewer
- [AGREE] pytest 전체 통과를 acceptance로 둠
- [CONCERN] Windows 런타임에서 installer 실제 설치 테스트는 CI에서 커버 안 됨

## 9. Performance Reviewer
- [CONCERN] dataset remove undo로 메모리 급증 위험 (세션 내만이라도 제약 필요)

## 10. Maintainability Reviewer
- [CONCERN] undo_manager가 호환성 때문에 복잡해짐 → 다음 마일스톤에서 정리 필요

## 11. Product Reviewer
- [AGREE] Undo/Redo 확대 + 배포는 사용자/개발자 모두에 큰 가치

## 12. Overall Reviewer
- 결론: **AGREE (조건부)**
  - 단기적으로 ship OK
  - 다음 개선 우선순위: (1) 호환 레이어 제거/정리 (2) 메모리 안전장치 (3) 업데이트 무결성/링크 UX
