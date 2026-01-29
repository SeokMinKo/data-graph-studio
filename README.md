# Data Graph Studio 📊

> 1000만 행 이상의 빅데이터도 부드럽게 시각화하는 도구

## ✨ 주요 기능

- 🚀 **빅데이터 처리** - 1000만 행 이상 데이터 지원
- 📊 **드래그 앤 드롭 시각화** - 코딩 없이 강력한 차트 생성
- 🔄 **양방향 연동** - 그래프 ↔ 테이블 실시간 동기화
- 📈 **다양한 차트** - Line, Bar, Scatter, Pie, Heatmap 등
- 🎯 **스마트 필터링** - 다중 조건 필터, 검색
- 💾 **메모리 최적화** - 타입 다운캐스팅, 가상 스크롤

## 🖥️ 스크린샷

```
┌─────────────────────────────────────────────────────────────┐
│  📊 SUMMARY                                                 │
│  Rows: 10,000,000 │ Selected: 1,234 │ Memory: 2.1 GB       │
├─────────────────────────────────────────────────────────────┤
│ Options │         📈 MAIN GRAPH                  │ Stats   │
│ X-Axis  │  🔍 ✋ ▢ 〰️ ✕ 🔄 ⊡                     │ Hist    │
│ Type    │         [Interactive Chart]            │ Box     │
│ Style   │                                        │ Violin  │
├─────────────────────────────────────────────────────────────┤
│ GROUP   │              📋 TABLE                  │ VALUE   │
│ ZONE    │  Col1 │ Col2 │ Col3 │ Col4 │ ...     │ ZONE    │
│ Region  │  ...  │ ...  │ ...  │ ...  │         │ Sales   │
│ Date    │  ...  │ ...  │ ...  │ ...  │         │ (SUM)   │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 설치

```bash
# 저장소 클론
git clone https://github.com/godol/data-graph-studio.git
cd data-graph-studio

# 가상환경 생성
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r requirements.txt

# 또는 개발 모드 설치
pip install -e ".[dev]"
```

## 📖 사용법

### 실행

```bash
# GUI 실행
python main.py

# 파일과 함께 실행
python main.py data.csv
```

### 기본 워크플로우

1. **데이터 로드**
   - `File > Open` 또는 파일 드래그 앤 드롭
   - 지원 포맷: CSV, Excel, Parquet, JSON

2. **그룹화 (Group Zone)**
   - 테이블 헤더를 왼쪽 Group Zone으로 드래그
   - 여러 컬럼으로 계층적 그룹화 가능

3. **값 설정 (Value Zone)**
   - 숫자 컬럼을 오른쪽 Value Zone으로 드래그
   - 집계 함수 선택 (SUM, AVG, MAX 등)

4. **X축 설정**
   - 왼쪽 옵션 패널에서 X축 컬럼 선택

5. **차트 타입 변경**
   - 툴바 또는 옵션 패널에서 선택

### 선택 도구

| 도구 | 단축키 | 설명 |
|------|--------|------|
| 🔍 Zoom | Z | 영역 확대 |
| ✋ Pan | H | 이동 |
| ▢ Rect Select | R | 사각형 선택 |
| 〰️ Lasso Select | L | 자유 곡선 선택 |
| ✕ Deselect | Escape | 선택 해제 |
| 🔄 Reset | Home | 뷰 초기화 |
| ⊡ Autofit | F | 자동 맞춤 |

### 단축키

| 키 | 동작 |
|----|------|
| Ctrl+O | 파일 열기 |
| Ctrl+S | 프로젝트 저장 |
| Ctrl+F | 검색 |
| Ctrl+A | 전체 선택 |
| Escape | 선택 해제 |

## 🔧 기술 스택

- **UI**: PySide6 (Qt 6)
- **Data Engine**: Polars (고성능 DataFrame)
- **Charts**: PyQtGraph (실시간) + Plotly (내보내기)
- **File I/O**: Apache Arrow, OpenPyXL

## 📊 성능 목표

| 데이터 크기 | 로딩 | 필터/정렬 | 메모리 |
|------------|------|----------|--------|
| 10만 행 | < 1초 | < 0.3초 | < 200MB |
| 100만 행 | < 5초 | < 1초 | < 1GB |
| 1000만 행 | < 30초 | < 3초 | < 4GB |

## 📁 프로젝트 구조

```
data-graph-studio/
├── main.py              # 진입점
├── src/
│   ├── core/
│   │   ├── data_engine.py   # Polars 데이터 엔진
│   │   └── state.py         # 앱 상태 관리
│   ├── ui/
│   │   ├── main_window.py   # 메인 윈도우
│   │   └── panels/
│   │       ├── summary_panel.py
│   │       ├── graph_panel.py
│   │       └── table_panel.py
│   ├── graph/
│   │   └── sampling.py      # 샘플링 알고리즘
│   └── utils/
│       └── memory.py        # 메모리 모니터링
├── tests/
├── requirements.txt
└── PRD.md               # 제품 요구사항
```

## 🧪 테스트

```bash
# 테스트 실행
pytest

# 커버리지 포함
pytest --cov=src
```

## 🗺️ 로드맵

- [x] Phase 1: Core + Big Data Foundation
- [ ] Phase 2: Visualization + Interaction
- [ ] Phase 3: Advanced Features
- [ ] Phase 4: Pro + Polish

자세한 내용은 [PRD.md](PRD.md) 참조

## 📄 라이선스

MIT License

## 🤝 기여

이슈와 PR을 환영합니다!
