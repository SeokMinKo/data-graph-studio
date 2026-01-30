# PRD: External Integration & Interoperability

## 개요

Data Graph Studio를 다른 프로그램/도구와 쉽게 연동할 수 있도록 다양한 통합 인터페이스를 제공합니다.

## 목표

1. **자동화 지원**: 스크립트/배치 작업에서 그래프 생성 자동화
2. **데이터 파이프라인 통합**: ETL 도구, 분석 스크립트와 연동
3. **협업 도구 연동**: 리포트, 문서 작성 도구와 통합
4. **개발자 친화적**: API를 통한 프로그래매틱 제어

---

## 기능 요구사항

### 1. CLI (Command Line Interface)

**목적**: 터미널/스크립트에서 직접 그래프 생성

```bash
# 기본 사용
dgs plot data.csv -x Time -y Value -o output.png

# 차트 타입 지정
dgs plot data.csv --chart bar -x Category -y Sales -o chart.png

# 여러 Y 컬럼
dgs plot data.csv -x Time -y "Read_IOPS,Write_IOPS" --chart line

# 프로필 적용
dgs plot data.csv --profile "storage_analysis" -o report.png

# 설정 파일 사용
dgs plot data.csv --config settings.json

# 배치 처리
dgs batch input_folder/ --output output_folder/ --config batch.json

# 데이터 정보 확인
dgs info data.csv

# 데이터 변환
dgs convert data.csv -o data.parquet
dgs convert data.xlsx -o data.csv --sheet "Sheet1"
```

**주요 옵션**:
| 옵션 | 설명 |
|------|------|
| `-x, --x-column` | X축 컬럼 |
| `-y, --y-columns` | Y축 컬럼 (쉼표로 구분) |
| `-c, --chart` | 차트 타입 (line, bar, scatter, pie, area, histogram) |
| `-o, --output` | 출력 파일 (png, jpg, svg, pdf) |
| `--width, --height` | 이미지 크기 |
| `--title` | 차트 제목 |
| `--profile` | 저장된 프로필 이름 |
| `--config` | JSON 설정 파일 |
| `--headless` | GUI 없이 실행 |

---

### 2. Python API

**목적**: Python 스크립트/Jupyter에서 직접 사용

```python
from data_graph_studio import DataGraphStudio, Chart

# 방법 1: 간단한 플로팅
dgs = DataGraphStudio()
dgs.load("data.csv")
dgs.plot(x="Time", y=["Read_IOPS", "Write_IOPS"], chart="line")
dgs.save("output.png")

# 방법 2: pandas 연동
import pandas as pd
df = pd.read_csv("data.csv")
dgs.plot_dataframe(df, x="Time", y="Value")

# 방법 3: Polars 연동
import polars as pl
df = pl.read_csv("data.csv")
dgs.plot_polars(df, x="Time", y="Value")

# 방법 4: 체이닝
(DataGraphStudio()
    .load("data.csv")
    .filter("Device == 'SSD'")
    .plot(x="Time", y="IOPS", chart="line")
    .set_title("SSD Performance")
    .save("ssd_perf.png"))

# 방법 5: 설정 딕셔너리
config = {
    "data": "data.csv",
    "x": "Time",
    "y": ["Value1", "Value2"],
    "chart": "bar",
    "title": "Comparison",
    "output": "chart.png"
}
DataGraphStudio.from_config(config).render()

# 방법 6: 프로필 사용
dgs.load_profile("my_profile.json")
dgs.apply_to("new_data.csv")
dgs.save("output.png")

# 방법 7: 비교 분석
dgs.compare(["data1.csv", "data2.csv"], 
            x="Time", y="Value", 
            labels=["Before", "After"])

# 방법 8: Jupyter 인라인 표시
dgs.show()  # Jupyter에서 인라인 표시
```

**클래스 구조**:
```python
class DataGraphStudio:
    def load(path: str) -> Self
    def load_dataframe(df: pd.DataFrame) -> Self
    def load_polars(df: pl.DataFrame) -> Self
    def plot(x: str, y: list, chart: str = "line") -> Self
    def filter(expr: str) -> Self
    def set_title(title: str) -> Self
    def set_axis_labels(x: str, y: str) -> Self
    def save(path: str, format: str = None) -> None
    def show() -> None  # Jupyter/IPython
    def to_image() -> bytes
    def get_state() -> dict
```

---

### 3. REST API Server

**목적**: 웹 서비스, 다른 언어에서 HTTP로 접근

```bash
# 서버 시작
dgs server --port 8080

# 또는 앱 내에서 활성화
# Settings > API Server > Enable
```

**엔드포인트**:

```
POST /api/v1/plot
  - 데이터와 설정을 받아 이미지 반환

GET /api/v1/status
  - 서버 상태 확인

POST /api/v1/data/load
  - 데이터 파일 업로드

GET /api/v1/data/info
  - 현재 로드된 데이터 정보

POST /api/v1/export
  - 다양한 포맷으로 내보내기

GET /api/v1/profiles
  - 저장된 프로필 목록

POST /api/v1/profiles/{name}/apply
  - 프로필 적용
```

**예시 요청**:
```bash
# 그래프 생성
curl -X POST http://localhost:8080/api/v1/plot \
  -F "data=@data.csv" \
  -F "config={\"x\":\"Time\",\"y\":[\"Value\"],\"chart\":\"line\"}" \
  -o output.png

# JSON 데이터로 그래프 생성
curl -X POST http://localhost:8080/api/v1/plot \
  -H "Content-Type: application/json" \
  -d '{
    "data": [[1,10],[2,20],[3,15]],
    "columns": ["x", "y"],
    "x": "x",
    "y": ["y"],
    "chart": "line"
  }' \
  -o output.png
```

---

### 4. Clipboard Integration

**목적**: 복사/붙여넣기로 빠른 데이터 교환

**지원 포맷**:
- **입력**: 
  - Excel/Google Sheets에서 복사한 테이블
  - CSV/TSV 텍스트
  - JSON 배열
  
- **출력**:
  - 이미지 (PNG)
  - 데이터 (CSV/TSV)
  - 설정 (JSON)

**단축키**:
| 단축키 | 기능 |
|--------|------|
| `Ctrl+V` | 클립보드에서 데이터 붙여넣기 |
| `Ctrl+Shift+V` | 클립보드에서 설정 붙여넣기 |
| `Ctrl+C` | 선택 영역 데이터 복사 |
| `Ctrl+Shift+C` | 현재 그래프 이미지 복사 |
| `Ctrl+Alt+C` | 현재 설정 JSON 복사 |

---

### 5. File Associations & Drag-Drop

**파일 연결**:
- `.dgs` - Data Graph Studio 프로젝트 파일
- `.dgsp` - Data Graph Studio 프로필
- 더블클릭으로 앱 실행 및 파일 열기

**드래그 앤 드롭**:
- 데이터 파일을 앱으로 드래그하면 자동 로드
- 프로필 파일 드래그하면 설정 적용
- 이미지를 외부로 드래그하여 내보내기

**지원 입력 포맷**:
| 포맷 | 확장자 | 설명 |
|------|--------|------|
| CSV | .csv | 쉼표 구분 |
| TSV | .tsv, .txt | 탭 구분 |
| Excel | .xlsx, .xls | 스프레드시트 |
| Parquet | .parquet | 컬럼 저장 |
| JSON | .json | JSON 배열/객체 |
| SQLite | .db, .sqlite | 데이터베이스 |

---

### 6. Export Formats

**이미지**:
| 포맷 | 용도 |
|------|------|
| PNG | 일반 이미지, 프레젠테이션 |
| SVG | 벡터, 웹, 편집 가능 |
| PDF | 문서, 인쇄 |
| EPS | 출판, LaTeX |

**데이터**:
| 포맷 | 용도 |
|------|------|
| CSV | 범용 |
| Excel | 스프레드시트 |
| JSON | API, 웹 |
| Parquet | 빅데이터, 분석 |

**리포트**:
| 포맷 | 용도 |
|------|------|
| DOCX | Word 문서 |
| PPTX | PowerPoint |
| HTML | 웹 리포트 |
| Markdown | 문서화 |

---

### 7. Watch Mode (파일 감시)

**목적**: 파일 변경 시 자동 그래프 업데이트

```bash
# CLI에서
dgs watch data.csv --output live_chart.png --interval 5

# 또는 앱 내에서
# File > Watch Mode > Enable
```

**사용 사례**:
- 실시간 로그 모니터링
- 벤치마크 진행 중 결과 시각화
- CI/CD 파이프라인 연동

---

### 8. Plugin System

**목적**: 사용자 정의 기능 확장

**플러그인 타입**:
1. **Data Source**: 새로운 데이터 소스 지원
2. **Chart Type**: 커스텀 차트 타입
3. **Export Format**: 새로운 내보내기 포맷
4. **Transform**: 데이터 변환 함수

**플러그인 구조**:
```
plugins/
  my_plugin/
    __init__.py
    plugin.json
    main.py
```

**plugin.json**:
```json
{
  "name": "My Custom Chart",
  "version": "1.0.0",
  "type": "chart",
  "entry": "main.py",
  "author": "Your Name"
}
```

---

### 9. Integration Examples

#### Jupyter Notebook
```python
from data_graph_studio import dgs_magic

# 매직 커맨드 사용
%load_ext data_graph_studio

%%dgs
data: my_dataframe
x: timestamp
y: [cpu_usage, memory_usage]
chart: line
title: System Metrics
```

#### Shell Script (배치 처리)
```bash
#!/bin/bash
for file in data/*.csv; do
    name=$(basename "$file" .csv)
    dgs plot "$file" -x Time -y Value -o "output/${name}.png"
done
```

#### Python 자동화
```python
import subprocess
from pathlib import Path

# 여러 파일 처리
for csv_file in Path("data").glob("*.csv"):
    subprocess.run([
        "dgs", "plot", str(csv_file),
        "-x", "Time", "-y", "Value",
        "-o", f"output/{csv_file.stem}.png"
    ])
```

#### Excel/VBA
```vba
Sub CreateChart()
    Shell "dgs plot ""C:\data\sales.csv"" -x Month -y Revenue -o ""C:\charts\sales.png"""
End Sub
```

#### PowerShell
```powershell
# 모든 CSV 파일 처리
Get-ChildItem *.csv | ForEach-Object {
    dgs plot $_.FullName -x Time -y Value -o "output\$($_.BaseName).png"
}
```

---

## 우선순위

| 순위 | 기능 | 이유 |
|------|------|------|
| P0 | CLI | 자동화의 기본 |
| P0 | Python API | 데이터 분석 워크플로우 |
| P1 | Clipboard | 빠른 데이터 교환 |
| P1 | Export 포맷 확장 | 다양한 도구 연동 |
| P2 | REST API | 웹/타 언어 연동 |
| P2 | Watch Mode | 실시간 모니터링 |
| P3 | Plugin System | 확장성 |

---

## 기술 스택

- **CLI**: `argparse` or `click`
- **REST API**: `FastAPI` or `Flask`
- **IPC**: 기존 TCP 서버 확장
- **Clipboard**: `pyperclip`, Qt Clipboard

---

## 마일스톤

### Phase 1: Core Integration (2주)
- [ ] CLI 기본 구현
- [ ] Python API 기본 구현
- [ ] Clipboard 입출력

### Phase 2: Extended Integration (2주)
- [ ] REST API 서버
- [ ] Watch Mode
- [ ] Export 포맷 확장

### Phase 3: Advanced (2주)
- [ ] Plugin System
- [ ] Jupyter 통합
- [ ] 배치 처리 최적화

---

## 성공 지표

1. CLI로 10개 파일 배치 처리 < 30초
2. Python API 3줄로 그래프 생성 가능
3. REST API 응답 시간 < 500ms
4. Clipboard 복사/붙여넣기 1초 이내
