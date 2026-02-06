# PRD v2: Zone을 Chart Options로 이전 + UI 개선

> **v2 변경사항**: 리뷰 Round 1 피드백 반영 (Group By 다중선택, Formula 입력, 스크롤 전략 등)

## 1. 목표
데이터 Zone (X-Axis, Value/Y-Axis, Group-By, Hover)을 Table Panel에서 제거하고 Chart Options 패널의 "Data" 탭으로 통합. 칩 기반 UI를 콤보박스/체크박스 기반으로 교체하여 가독성과 사용성 개선.

## 2. 배경
### 현재 구조
```
TablePanel:
┌──────────┬──────────┬─────────────────────┬────────────┬──────────┐
│  X Zone  │  Group   │     Data Table      │   Values   │  Hover   │
│ (150px)  │  Zone    │                     │   Zone     │  Zone    │
│          │ (150px)  │                     │  (180px)   │ (150px)  │
└──────────┴──────────┴─────────────────────┴────────────┴──────────┘
```

### 문제점
- Zone들이 테이블 좌우 공간을 차지 (~640px) → 테이블 데이터 볼 공간 부족
- ValueChipWidget 내 콤보박스/수식 입력이 180px zone에 맞지 않아 깨짐
- 드래그 앤 드롭 방식이 직관적이지 않음 (칩이 작고 다루기 어려움)
- Chart Options 패널과 데이터 설정이 분리되어 있어 왔다갔다 해야 함

### 변경 후 구조
```
TablePanel (Zone 제거됨):
┌─────────────────────────────────────────────────────────┐
│                      Data Table                         │
│                  (전체 너비 활용)                          │
└─────────────────────────────────────────────────────────┘

GraphOptionsPanel (Data 탭 추가, 너비 260~320px):
┌─────────────────────────────────┐
│  ⚙️ Chart Options               │
│  ┌────┬─────┬──────┬────┬─────┐ │
│  │Data│Chart│Legend│Axes│Style│ │
│  ├──────────────────────────┤  │
│  │ [Data 탭 내용 - 아래 참고] │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
```

## 3. 요구사항

### 3.1 기능 요구사항
- [ ] FR-1: GraphOptionsPanel에 "Data" 탭 추가 (첫 번째 탭)
- [ ] FR-2: X-Axis → QComboBox 드롭다운 (컬럼 목록 + "(Index)" 옵션, 내부값은 None)
- [ ] FR-3: Y-Axis(Values) → 스크롤 가능한 체크박스 리스트 (숫자형 컬럼만)
  - 각 체크된 항목: Aggregation 콤보 (SUM/AVG/COUNT/MIN/MAX) 인라인 표시
  - 각 체크된 항목: Formula 입력 (접기/펼치기 가능, 기본 접힘)
  - 전체 선택/해제 토글 버튼
- [ ] FR-4: Group By → 스크롤 가능한 체크박스 리스트 (다중 선택, 순서 유지)
  - 전체 선택/해제 토글 버튼
- [ ] FR-5: Hover → 스크롤 가능한 체크박스 리스트 (다중 선택)
  - 전체 선택/해제 토글 버튼
- [ ] FR-6: TablePanel에서 Zone 위젯 4개 제거 (XAxisZone, ValueZone, GroupZone, HoverZone)
- [ ] FR-7: TablePanel splitter 제거 → 단일 테이블 위젯만 남김
- [ ] FR-8: 테이블 헤더 우클릭 메뉴 기능 유지 ("Set as X" / "Add to Y-Axis" / "Add to Group" / "Add to Hover")
  - 우클릭 액션 후 Data 탭이 아닌 다른 탭이 활성화 상태여도 동작
  - 상태바에 "Added 'col1' to Y-Axis" 등 피드백 메시지 표시
- [ ] FR-9: Data 탭의 컬럼 목록은 engine.columns에서 자동으로 가져옴. 숫자형 여부는 engine.df.dtypes로 판별.
- [ ] FR-10: 기존 state 연동 유지 (state.x_column, state.value_columns, state.group_columns, state.hover_columns)
- [ ] FR-11: 데이터셋 전환 시 Data 탭 초기화 (이전 체크 상태 클리어, 새 컬럼으로 재구성)
- [ ] FR-12: 데이터 클리어 시 Data 탭 비활성화 (빈 상태)
- [ ] FR-13: 테이블 헤더에서 Ctrl+드래그 Zone 기능 제거 (코드 정리)

### 3.2 비기능 요구사항
- [ ] NFR-1: GraphOptionsPanel 너비 260~320px (기존 200~240px에서 확대)
- [ ] NFR-2: Data 탭 로딩 시 컬럼 200개에서 < 100ms
- [ ] NFR-3: 테마 (다크/라이트) 지원 유지
- [ ] NFR-4: 위젯 정리 시 signal disconnect 처리 (메모리 누수 방지)

## 4. 범위

### 포함
- GraphOptionsPanel에 Data 탭 추가
- DataTab 새 파일 생성 (`data_graph_studio/ui/panels/data_tab.py`)
- TablePanel에서 Zone 위젯 제거 및 레이아웃 단순화
- 테이블 헤더 우클릭 메뉴 연동
- 기존 state 시그널 연동
- Zone 관련 Ctrl+드래그 코드 제거

### 제외
- Zone 관련 기존 클래스 파일 삭제 (dead code 유지, 추후 정리)
- 새로운 데이터 변환/피벗 기능
- 가상 스크롤 (500+ 컬럼용, 현재 불필요)

## 5. UI/UX 상세

### Data 탭 레이아웃 (전체 QScrollArea 안에)
```
┌─ Data ────────────────────────────┐
│ ┌───────────── QScrollArea ─────┐ │
│ │                               │ │
│ │ X-Axis                        │ │
│ │ ┌───────────────────────────┐ │ │
│ │ │ (Index)                ▼  │ │ │
│ │ └───────────────────────────┘ │ │
│ │                               │ │
│ │ ─── separator (QFrame HLine) ─│ │
│ │                               │ │
│ │ Y-Axis (Values)    [All][None]│ │
│ │ ┌── max-height 200px, scroll ┐│ │
│ │ │ ☑ Temperature              ││ │
│ │ │   [SUM ▼] [▶ f(y)]        ││ │
│ │ │ ☑ Humidity                 ││ │
│ │ │   [AVG ▼] [▶ f(y)]        ││ │
│ │ │ □ Pressure                 ││ │
│ │ │ □ WindSpeed                ││ │
│ │ └────────────────────────────┘│ │
│ │                               │ │
│ │ ─── separator ────────────────│ │
│ │                               │ │
│ │ Group By             [All][None]│
│ │ ┌── max-height 120px, scroll ┐│ │
│ │ │ ☑ Region                   ││ │
│ │ │ □ Category                 ││ │
│ │ │ □ Date                     ││ │
│ │ └────────────────────────────┘│ │
│ │                               │ │
│ │ ─── separator ────────────────│ │
│ │                               │ │
│ │ Hover Columns        [All][None]│
│ │ ┌── max-height 120px, scroll ┐│ │
│ │ │ ☑ col1                     ││ │
│ │ │ ☑ col2                     ││ │
│ │ │ □ col3                     ││ │
│ │ └────────────────────────────┘│ │
│ └───────────────────────────────┘ │
└───────────────────────────────────┘
```

### Y-Axis 항목 상세 (체크된 상태)
```
┌─────────────────────────────┐
│ ☑ Temperature               │  ← 체크박스 + 컬럼명
│   [SUM ▼]  [▶ f(y)=...]     │  ← Agg 콤보 + Formula 토글
└─────────────────────────────┘
```
- 체크 해제 시: Agg/Formula 행 숨김 (체크박스 + 컬럼명만 표시)
- Formula 토글 `▶`: 클릭 시 `▼`로 변경되며 QLineEdit 표시
- Formula 기본값: 접힌 상태 (▶)

### 인터랙션
- **X-Axis 콤보박스**: "(Index)" 선택 시 `state.set_x_column(None)`. 내부적으로 "(Index)"는 sentinel None 값 사용.
- **Y-Axis 체크박스**: 체크 시 `state.add_value_column(name)`, 해제 시 `state.remove_value_column(name)`
- **Y-Axis Aggregation**: 변경 시 해당 ValueColumn의 aggregation 업데이트
- **Y-Axis Formula**: 편집 완료(editingFinished) 시 해당 ValueColumn의 formula 업데이트
- **Group By 체크박스**: 체크 시 `state.add_group_column(name)`, 해제 시 `state.remove_group_column(name)`. 다중 선택 지원.
- **Hover 체크박스**: 체크/해제 시 `state.hover_columns` 갱신
- **[All] 버튼**: 해당 섹션의 모든 항목 체크 (Y-Axis는 숫자형 컬럼만)
- **[None] 버튼**: 해당 섹션의 모든 항목 체크 해제
- **blockSignals**: 벌크 작업 시 (All/None, set_columns, _sync_from_state) blockSignals 사용
- **setUpdatesEnabled(False)**: 벌크 UI 업데이트 시 레이아웃 재계산 방지

### 테이블 헤더 우클릭 동작
- "Set as X-Axis" → Data 탭 X 콤보박스 변경 (활성 탭 전환 안 함)
- "Add to Y-Axis" → 해당 컬럼 체크 (이미 체크면 무시)
- "Add to Group" → 해당 컬럼 체크
- "Add to Hover" → 해당 컬럼 체크
- 모든 액션 후 상태바에 `"Added 'Temperature' to Y-Axis"` 피드백

### Separator 스타일
- `QFrame` with `HLine` shape
- 다크 테마: `#3E4A59` (border color)
- 라이트 테마: `#E2E8F0`

## 6. 데이터 구조

### 기존 State 인터페이스 (변경 없음)
```python
state.x_column: Optional[str]
state.value_columns: List[ValueColumn]
state.group_columns: List[GroupColumn]
state.hover_columns: List[str]
```

### 새로운 DataTab 클래스 (`data_graph_studio/ui/panels/data_tab.py`)
```python
class DataTab(QWidget):
    """Chart Options의 Data 탭 - X/Y/Group/Hover 설정"""
    
    def __init__(self, state: AppState):
        ...
    
    def set_columns(self, columns: List[str], engine: DataEngine):
        """데이터 로드 시 컬럼 목록 설정.
        engine.df.dtypes로 숫자형 여부 판별.
        기존 체크 상태 클리어 후 재구성."""
        ...
    
    def clear(self):
        """데이터 클리어 시 호출. 모든 위젯 비활성화."""
        ...
    
    def sync_from_state(self):
        """외부 state 변경(프로파일 적용 등) 시 UI 동기화"""
        ...
    
    def cleanup(self):
        """위젯 파괴 시 signal disconnect"""
        ...
```

## 7. 성능 & 메모리 요구사항
- 컬럼 200개 데이터셋에서 Data 탭 `set_columns()` < 100ms
- 체크박스 토글 시 state 변경 < 10ms
- 벌크 작업 시 `blockSignals` + `setUpdatesEnabled(False)` 필수
- 위젯 재생성 시 `deleteLater()` 사용
- Signal 연결은 `functools.partial` 선호 (lambda GC 이슈 방지)
- `cleanup()` 메서드로 명시적 signal disconnect
- 메모리 추가 < 1MB

## 8. 테스트 시나리오

### Unit Tests
- [ ] UT-1: DataTab 초기화 시 빈 상태로 생성
- [ ] UT-2: set_columns() 호출 시 콤보박스/체크리스트에 컬럼 반영
- [ ] UT-3: X-Axis 콤보박스 변경 시 state.set_x_column() 호출
- [ ] UT-4: Y-Axis 체크박스 토글 시 state.value_columns 변경
- [ ] UT-5: Aggregation 변경 시 해당 ValueColumn 업데이트
- [ ] UT-6: Formula 편집 시 해당 ValueColumn 업데이트
- [ ] UT-7: Group By 체크박스 다중 선택 시 state.group_columns 변경 (순서 유지)
- [ ] UT-8: Hover 체크박스 토글 시 state.hover_columns 변경
- [ ] UT-9: State 외부 변경 시 UI 동기화 (sync_from_state)
- [ ] UT-10: [All]/[None] 버튼 동작
- [ ] UT-11: 데이터셋 전환 시 Data 탭 초기화
- [ ] UT-12: cleanup() 호출 시 signal disconnect

### Integration Tests
- [ ] IT-1: 데이터 로드 → Data 탭에 컬럼 표시 → 선택 → 그래프 갱신
- [ ] IT-2: 프로파일 적용 시 Data 탭 UI 동기화
- [ ] IT-3: 테이블 헤더 우클릭 → state 변경 → Data 탭 반영
- [ ] IT-4: 위자드 완료 → state 변경 → Data 탭 반영

### E2E Tests
- [ ] E2E-1: 파일 로드 → Data 탭에서 X/Y/Group 설정 → 차트 올바르게 표시
- [ ] E2E-2: Data 탭에서 Y축 컬럼 여러 개 선택 → 멀티라인 차트 표시
- [ ] E2E-3: 프로파일 저장 → 다시 로드 → Data 탭 상태 복원

### Performance Tests
- [ ] PT-1: 200개 컬럼 데이터셋 로드 시 Data 탭 렌더링 < 100ms
- [ ] PT-2: 체크박스 연속 토글 10회 시 UI 응답성 유지

## 9. 성공 기준
- [ ] Zone이 TablePanel에서 완전 제거되고 테이블이 전체 너비 사용
- [ ] Data 탭에서 X/Y/Group/Hover 모두 설정 가능 (기존 기능 100% 커버)
- [ ] Group By 다중 선택 동작
- [ ] Y-Axis Formula 입력 동작
- [ ] 프로파일 저장/로드/위자드 연동 정상 동작
- [ ] 깔끔한 UI (깨짐 없음)
- [ ] 모든 테스트 통과

## 10. 미해결 질문
- 없음 (Round 1 리뷰 피드백 모두 반영됨)

---

# PRD 부록: WPR ETL 단계별 로딩 (Import Wizard)

## 1. 목표
- WPR(Window Performance Recorder) 파일을 **단계별로 명시적으로 로딩**한다.
- 대용량 WPR에서도 Import Wizard가 버벅이지 않도록 **변환/미리보기/본 로딩**을 분리한다.

## 2. 배경
- WPR 파일이 대용량이라 Import Wizard에서 한번에 로딩하면 UI가 멈춘다.
- WPAExporter 기반 변환 단계가 필요하다.

## 3. 요구사항
### 3.1 기능 요구사항
- [ ] FR-1: Import Wizard에 **WPR 변환 단계**를 추가한다.
- [ ] FR-2: 변환 도구는 **WPAExporter**를 기본 사용한다.
- [ ] FR-3: 변환 결과는 **Parquet**으로 저장한다.
- [ ] FR-4: 변환 후 **미리보기/샘플링**을 제공한다.
- [ ] FR-5: 변환 단계 진행 상태(진행 중/완료/실패)를 명확히 표시한다.

### 3.2 비기능 요구사항
- [ ] NFR-1: 변환 실패 시 오류 메시지를 사용자에게 명확히 보여준다.
- [ ] NFR-2: 변환 중에도 UI가 멈추지 않는다.

## 4. 범위
### 포함
- Import Wizard 단계 추가
- WPAExporter 경로 자동 탐색(환경변수/Path)
- Parquet 산출물 경로 저장

### 제외
- ETL 파서 내부 알고리즘 변경
- 분석/시각화 로직 변경

## 5. UI/UX 상세
- Wizard Step 순서: **파일 선택 → WPR 변환 → 미리보기/파싱 → 그래프 설정 → 완료**
- 변환 단계에서:
  - 입력 파일/출력 파일 경로 표시
  - "변환 시작" 버튼
  - 진행바(불확정/확정)
  - 실패 시 재시도 가능

## 6. 데이터 구조
- 변환 결과 파일: `{원본명}_wpr.parquet`

## 7. 성능 & 메모리 요구사항
- 변환 단계는 별도 프로세스로 실행(서브프로세스)

## 8. 테스트 시나리오
### Unit Tests
- [ ] UT-1: WPR 파일 경로 → Parquet 출력 경로 생성 로직
- [ ] UT-2: WPR 파일이면 Wizard에 변환 단계가 삽입됨

## 9. 성공 기준
- [ ] WPR 파일을 Import Wizard에서 단계별로 로딩 가능
- [ ] 변환 단계에서 UI 멈춤 없이 진행

## 10. 미해결 질문
- 없음
