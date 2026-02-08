# Pre-mortem — Undo/Redo 확대 + Windows 설치형 배포/자동 업데이트

Date: 2026-02-09

이 문서는 “이 기능이 2주 뒤 실패했다면 왜 실패했을까?”를 가정해 리스크를 사전에 제거하기 위한 체크리스트다.

## 1) Undo/Redo가 사용자에게 신뢰를 못 얻음

### 실패 시나리오
- Ctrl+Z를 눌렀는데 화면만 바뀌고 내부 상태가 꼬이거나, 일부만 되돌아가서 사용자가 불신한다.

### 원인 가설
- 상태 변경 중 signal 재진입 → undo 기록이 다시 쌓여 루프
- state snapshot이 불완전 (예: table columns 갱신 누락)
- 여러 패널이 서로 다른 상태 소스를 바라봄

### 예방
- UndoStack `pause()` 가드를 replay 시 항상 사용
- AppState 기반 변경은 snapshot을 명확히 한 뒤 복원 시 동일 signal을 emit
- computed column처럼 DF swap이 필요한 것은 “UI sync helper”로 공통화

## 2) Dataset remove undo가 메모리 폭탄

### 실패 시나리오
- 대용량 데이터셋 삭제 후 undo를 위해 DF를 잡아두다가 메모리 급증/크래시

### 예방
- 세션 한정 + max_depth 제한(기본 200)
- 대형 DF를 가진 dataset remove command는 depth에서 우선 제거하거나, “undo 불가” 경고 옵션 고려

## 3) Windows 빌드 실패/Release 자산 누락

### 실패 시나리오
- PyInstaller가 숨은 의존성(특히 PySide6, polars/pyarrow)을 못 챙겨 빌드 실패
- Inno Setup 컴파일 경로가 runner에서 달라 실패
- Release에 자산 업로드가 누락되어 auto update가 동작 안 함

### 예방
- `dgs.spec` hiddenimports/datas를 지속 유지
- CI에서 pyinstaller 로그를 artifact로 남기기(추가 개선)
- release 업로드 step에서 glob 패턴을 명확히 유지

## 4) Auto update가 오탐/미탐

### 실패 시나리오
- 최신 릴리즈에 installer asset이 없거나 이름이 바뀌어 업데이트 체크가 항상 실패
- semantic version parsing 실패

### 예방
- asset prefix 규칙을 문서화/고정
- 업데이트 UI에서 “왜 실패했는지”를 보여주고, release 페이지 링크 제공(추가 개선)

## 5) 설치 실행 후 앱 종료/재실행 문제

### 실패 시나리오
- 인스톨러 실행은 되는데 앱이 닫히지 않거나 파일 잠금으로 설치 실패

### 예방
- installer 실행 직후 app close
- 더 안전하게는 별도 updater stub 프로세스 도입(장기)
