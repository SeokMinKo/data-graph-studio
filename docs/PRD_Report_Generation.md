# PRD: Report Generation Feature (레포트 생성 기능)

## 1. 개요

### 1.1 기능 요약
Data Graph Studio의 분석 결과를 다양한 형식의 전문적인 레포트로 내보내는 기능. 데이터 요약, 시각화, 통계 분석, 멀티 데이터 비교 결과를 포함한 종합 레포트를 생성한다.

### 1.2 핵심 가치
| 가치 | 설명 |
|------|------|
| **원클릭 레포트** | 복잡한 분석 결과를 한 번의 클릭으로 전문적인 문서로 변환 |
| **다양한 형식** | HTML, PDF, Word(DOCX), PowerPoint(PPTX) 등 업무 환경에 맞는 포맷 지원 |
| **템플릿 시스템** | 기업 브랜딩, 표준 레이아웃을 적용할 수 있는 템플릿 |
| **멀티데이터 비교** | 여러 데이터셋 비교 분석 결과의 시각적 표현 |

### 1.3 지원 형식
```
┌─────────────────────────────────────────────────────────────────┐
│                    Report Export Formats                        │
├─────────┬─────────┬─────────┬─────────┬─────────┬──────────────┤
│  HTML   │   PDF   │  DOCX   │  PPTX   │  JSON   │   Markdown   │
│Interactive│ Print │ Editable│Presentation│ Data  │   Readable   │
└─────────┴─────────┴─────────┴─────────┴─────────┴──────────────┘
```

---

## 2. 레포트 구조

### 2.1 표준 레포트 템플릿

```
┌─────────────────────────────────────────────────────────────────┐
│                         REPORT HEADER                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 로고 | 레포트 제목 | 생성일시 | 작성자                    │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      EXECUTIVE SUMMARY                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 핵심 발견 사항 (Key Findings)                          │   │
│  │ • 주요 수치 요약 (Key Metrics)                           │   │
│  │ • 결론 및 권장사항 (Conclusions)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      DATA OVERVIEW                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Total Rows  │  │  Columns    │  │ Date Range  │             │
│  │  1,234,567  │  │     25      │  │ 2024-01~12  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
├─────────────────────────────────────────────────────────────────┤
│                    STATISTICAL SUMMARY                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Column    │  Mean   │ Median │  Std  │  Min  │   Max   │   │
│  ├───────────┼─────────┼────────┼───────┼───────┼─────────┤   │
│  │ Sales     │ 45,230  │ 42,100 │ 12,500│ 1,200 │ 125,000 │   │
│  │ Quantity  │   152   │   145  │   35  │   10  │   500   │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      VISUALIZATIONS                             │
│  ┌───────────────────────┐  ┌───────────────────────┐          │
│  │                       │  │                       │          │
│  │    Main Chart         │  │   Distribution        │          │
│  │    (Line/Bar/etc)     │  │   (Histogram/Box)     │          │
│  │                       │  │                       │          │
│  └───────────────────────┘  └───────────────────────┘          │
│  ┌───────────────────────┐  ┌───────────────────────┐          │
│  │                       │  │                       │          │
│  │   Composition         │  │   Correlation         │          │
│  │   (Pie/Donut)         │  │   (Heatmap)           │          │
│  │                       │  │                       │          │
│  └───────────────────────┘  └───────────────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│                    COMPARISON ANALYSIS                          │
│  (멀티데이터 비교 시 포함)                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Dataset Comparison Matrix                               │   │
│  │ Statistical Test Results (t-test, p-values)             │   │
│  │ Difference Analysis Charts                              │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      DATA TABLES                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Top N Records / Grouped Summary / Pivot Table           │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                        APPENDIX                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • 분석 방법론 (Methodology)                              │   │
│  │ • 데이터 품질 노트 (Data Quality Notes)                  │   │
│  │ • 용어 정의 (Glossary)                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 레포트 섹션 상세

#### Section 1: Header (헤더)
| 필드 | 설명 | 필수 |
|------|------|------|
| report_title | 레포트 제목 | O |
| subtitle | 부제목 | X |
| author | 작성자 | X |
| created_at | 생성 일시 | O (자동) |
| logo | 회사/프로젝트 로고 | X |
| version | 버전 번호 | X |

#### Section 2: Executive Summary (요약)
| 필드 | 설명 |
|------|------|
| key_findings | 핵심 발견 사항 (자동 생성 + 사용자 입력) |
| key_metrics | 주요 지표 카드 (Total, Average, Max, Min 등) |
| conclusions | 결론 (사용자 입력) |
| recommendations | 권장사항 (사용자 입력) |

#### Section 3: Data Overview (데이터 개요)
| 필드 | 설명 |
|------|------|
| dataset_info | 데이터셋 메타데이터 (파일명, 경로, 크기) |
| row_count | 총 행 수 |
| column_count | 총 열 수 |
| date_range | 날짜 범위 (날짜 컬럼 존재 시) |
| data_types | 컬럼별 데이터 타입 요약 |
| missing_values | 결측값 현황 |

#### Section 4: Statistical Summary (통계 요약)
| 통계 | 설명 |
|------|------|
| descriptive | 기술 통계 (count, sum, mean, median, std, min, max, q1, q3) |
| distribution | 분포 특성 (skewness, kurtosis) |
| outliers | 이상치 정보 (IQR 기반) |
| trends | 트렌드 분석 (시계열 데이터) |

#### Section 5: Visualizations (시각화)
| 차트 유형 | 포함 조건 |
|----------|----------|
| main_chart | 현재 활성화된 메인 차트 |
| distribution_charts | X/Y 축 분포 히스토그램 |
| composition_chart | 파이/도넛 차트 (그룹 데이터) |
| correlation_heatmap | 상관관계 히트맵 (수치 컬럼 3개 이상) |
| trend_chart | 시계열 트렌드 (날짜 컬럼 존재 시) |
| box_plots | 그룹별 박스플롯 |

#### Section 6: Comparison Analysis (비교 분석) - 멀티데이터
| 섹션 | 설명 |
|------|------|
| dataset_matrix | 데이터셋 비교 매트릭스 |
| statistical_tests | 통계 검정 결과 (t-test, Mann-Whitney, KS) |
| effect_sizes | 효과 크기 (Cohen's d) |
| correlation_comparison | 데이터셋 간 상관관계 비교 |
| difference_analysis | 차이 분석 (Positive/Negative/Neutral) |
| overlay_charts | 오버레이 비교 차트 |
| side_by_side | 병렬 비교 뷰 |

#### Section 7: Data Tables (데이터 테이블)
| 테이블 유형 | 설명 |
|------------|------|
| top_n_records | 상위 N개 레코드 |
| grouped_summary | 그룹별 요약 |
| pivot_table | 피벗 테이블 |
| filtered_data | 필터링된 데이터 |
| cross_tabulation | 교차표 |

#### Section 8: Appendix (부록)
| 항목 | 설명 |
|------|------|
| methodology | 사용된 분석 방법론 설명 |
| data_quality | 데이터 품질 관련 노트 |
| glossary | 용어 정의 |
| filters_applied | 적용된 필터 목록 |
| calculation_formulas | 계산 필드 공식 |

---

## 3. 형식별 상세 스펙

### 3.1 HTML Report

```
┌─────────────────────────────────────────────────────────────────┐
│                      HTML Report Features                       │
├─────────────────────────────────────────────────────────────────┤
│ • Self-contained single HTML file                               │
│ • Embedded CSS (light/dark theme support)                       │
│ • Interactive charts via Plotly.js (embedded)                   │
│ • Responsive layout (mobile-friendly)                           │
│ • Table of contents with navigation                             │
│ • Collapsible sections                                          │
│ • Print-friendly stylesheet                                     │
│ • Data tables with sorting/filtering (optional)                 │
└─────────────────────────────────────────────────────────────────┘
```

**기술 구현:**
```python
class HTMLReportGenerator:
    """HTML 레포트 생성기"""

    def generate(self, report_data: ReportData, options: HTMLOptions) -> str:
        """
        Args:
            report_data: 레포트 데이터
            options: HTML 옵션
                - theme: "light" | "dark" | "auto"
                - interactive_charts: bool (Plotly 사용 여부)
                - include_data_tables: bool
                - toc_enabled: bool
                - collapsible_sections: bool

        Returns:
            완전한 HTML 문자열 (self-contained)
        """
```

### 3.2 PDF Report

```
┌─────────────────────────────────────────────────────────────────┐
│                       PDF Report Features                       │
├─────────────────────────────────────────────────────────────────┤
│ • High-quality vector graphics                                  │
│ • Page numbers and headers/footers                              │
│ • Table of contents with hyperlinks                             │
│ • Chart image embedding (PNG/SVG)                               │
│ • Multiple page sizes (A4, Letter, Legal)                       │
│ • Portrait/Landscape orientation                                │
│ • Customizable margins                                          │
│ • Watermark support                                             │
│ • Font embedding (Korean support)                               │
└─────────────────────────────────────────────────────────────────┘
```

**기술 구현:**
```python
class PDFReportGenerator:
    """PDF 레포트 생성기 (WeasyPrint 또는 ReportLab 사용)"""

    def generate(self, report_data: ReportData, options: PDFOptions) -> bytes:
        """
        Args:
            report_data: 레포트 데이터
            options: PDF 옵션
                - page_size: "A4" | "letter" | "legal"
                - orientation: "portrait" | "landscape"
                - margins: Margins (top, bottom, left, right)
                - header_footer: bool
                - watermark: Optional[str]
                - font_family: str

        Returns:
            PDF 바이트 데이터
        """
```

### 3.3 Word (DOCX) Report

```
┌─────────────────────────────────────────────────────────────────┐
│                      Word Report Features                       │
├─────────────────────────────────────────────────────────────────┤
│ • Editable document format                                      │
│ • Style-based formatting                                        │
│ • Table of contents (auto-update)                               │
│ • Embedded charts as images                                     │
│ • Professional table styling                                    │
│ • Header/footer with page numbers                               │
│ • Section breaks for layout control                             │
│ • Template support (.dotx)                                      │
│ • Track changes compatibility                                   │
└─────────────────────────────────────────────────────────────────┘
```

**기술 구현:**
```python
class DOCXReportGenerator:
    """Word 문서 생성기 (python-docx 사용)"""

    def generate(self, report_data: ReportData, options: DOCXOptions) -> bytes:
        """
        Args:
            report_data: 레포트 데이터
            options: DOCX 옵션
                - template_path: Optional[str] (템플릿 파일)
                - style_set: "professional" | "modern" | "minimal"
                - include_toc: bool
                - header_text: Optional[str]
                - footer_text: Optional[str]

        Returns:
            DOCX 바이트 데이터
        """
```

### 3.4 PowerPoint (PPTX) Report

```
┌─────────────────────────────────────────────────────────────────┐
│                   PowerPoint Report Features                    │
├─────────────────────────────────────────────────────────────────┤
│ • Presentation-ready slides                                     │
│ • Title slide with metadata                                     │
│ • Executive summary slide                                       │
│ • One chart per slide (optimal readability)                     │
│ • Key findings bullet points                                    │
│ • Comparison slides (side-by-side)                              │
│ • Data table slides (paginated)                                 │
│ • Master slide/theme support                                    │
│ • Speaker notes (optional)                                      │
│ • Animation-ready (no auto-animation)                           │
└─────────────────────────────────────────────────────────────────┘
```

**슬라이드 구성:**
```
Slide 1: Title
┌─────────────────────────────────────────┐
│                                         │
│          [REPORT TITLE]                 │
│          [Subtitle]                     │
│                                         │
│    Author: ___    Date: ___             │
│                                         │
└─────────────────────────────────────────┘

Slide 2: Executive Summary
┌─────────────────────────────────────────┐
│ Executive Summary                       │
│ ─────────────────                       │
│ • Key Finding 1                         │
│ • Key Finding 2                         │
│ • Key Finding 3                         │
│                                         │
│ ┌────┐ ┌────┐ ┌────┐ ┌────┐            │
│ │Rows│ │Cols│ │Avg │ │Max │            │
│ │1.2M│ │ 25 │ │45K │ │125K│            │
│ └────┘ └────┘ └────┘ └────┘            │
└─────────────────────────────────────────┘

Slide 3-N: Charts
┌─────────────────────────────────────────┐
│ [Chart Title]                           │
│ ┌───────────────────────────────────┐  │
│ │                                   │  │
│ │           [CHART]                 │  │
│ │                                   │  │
│ │                                   │  │
│ └───────────────────────────────────┘  │
│ Key insight: ___________________        │
└─────────────────────────────────────────┘

Slide N+1: Comparison (멀티데이터)
┌─────────────────────────────────────────┐
│ Dataset Comparison                      │
│ ┌─────────────┐  ┌─────────────┐       │
│ │ Dataset A   │  │ Dataset B   │       │
│ │  [CHART]    │  │  [CHART]    │       │
│ └─────────────┘  └─────────────┘       │
│                                         │
│ p-value: 0.003 ** (Significant)        │
└─────────────────────────────────────────┘
```

**기술 구현:**
```python
class PPTXReportGenerator:
    """PowerPoint 생성기 (python-pptx 사용)"""

    def generate(self, report_data: ReportData, options: PPTXOptions) -> bytes:
        """
        Args:
            report_data: 레포트 데이터
            options: PPTX 옵션
                - template_path: Optional[str]
                - slide_size: "16:9" | "4:3"
                - theme: "professional" | "modern" | "dark"
                - include_speaker_notes: bool
                - one_chart_per_slide: bool
                - include_data_tables: bool

        Returns:
            PPTX 바이트 데이터
        """
```

### 3.5 JSON Report (데이터 형식)

```python
{
    "report_metadata": {
        "title": "Sales Analysis Report",
        "author": "Data Team",
        "created_at": "2024-01-15T10:30:00Z",
        "version": "1.0",
        "generator": "Data Graph Studio v0.1.0"
    },
    "data_overview": {
        "datasets": [...],
        "total_rows": 1234567,
        "columns": [...],
        "date_range": {...}
    },
    "statistics": {
        "descriptive": {...},
        "distributions": {...}
    },
    "comparisons": {
        "datasets": [...],
        "statistical_tests": [...],
        "differences": [...]
    },
    "visualizations": {
        "charts": [
            {
                "type": "line",
                "title": "Sales Trend",
                "data": {...},
                "image_base64": "..."
            }
        ]
    },
    "tables": [...],
    "appendix": {...}
}
```

### 3.6 Markdown Report

```markdown
# [Report Title]

**Author:** [Author Name]
**Date:** [Generated Date]
**Data Source:** [File Path]

---

## Executive Summary

### Key Findings
- Finding 1
- Finding 2

### Key Metrics
| Metric | Value |
|--------|-------|
| Total Rows | 1,234,567 |
| Columns | 25 |

---

## Data Overview
...

## Statistical Analysis
...

## Visualizations
![Chart 1](./images/chart1.png)
...
```

---

## 4. 멀티데이터 비교 레포트

### 4.1 비교 레포트 특화 섹션

```
┌─────────────────────────────────────────────────────────────────┐
│                  MULTI-DATA COMPARISON REPORT                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  DATASET OVERVIEW                        │   │
│  ├──────────┬──────────┬──────────┬──────────┬─────────────┤   │
│  │ Dataset  │  Rows    │  Cols    │  Size    │   Color     │   │
│  ├──────────┼──────────┼──────────┼──────────┼─────────────┤   │
│  │ Sales Q1 │ 125,000  │   12     │  45 MB   │    🔵       │   │
│  │ Sales Q2 │ 132,000  │   12     │  48 MB   │    🟠       │   │
│  │ Sales Q3 │ 145,000  │   12     │  52 MB   │    🟢       │   │
│  └──────────┴──────────┴──────────┴──────────┴─────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              DESCRIPTIVE STATISTICS COMPARISON           │   │
│  ├──────────┬───────────────┬───────────────┬─────────────┤   │
│  │  Column  │   Sales Q1    │   Sales Q2    │   Sales Q3  │   │
│  ├──────────┼───────────────┼───────────────┼─────────────┤   │
│  │  Mean    │    45,230     │    48,500 ▲   │   52,100 ▲  │   │
│  │  Median  │    42,100     │    45,200 ▲   │   49,800 ▲  │   │
│  │  Std     │    12,500     │    13,200     │   14,100    │   │
│  │  Max     │   125,000     │   138,000 ▲   │  152,000 ▲  │   │
│  └──────────┴───────────────┴───────────────┴─────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 STATISTICAL TEST RESULTS                 │   │
│  ├───────────────┬─────────────┬────────────┬─────────────┤   │
│  │ Comparison    │  Test Type  │  p-value   │ Significant │   │
│  ├───────────────┼─────────────┼────────────┼─────────────┤   │
│  │ Q1 vs Q2      │   t-test    │   0.023    │    * Yes    │   │
│  │ Q1 vs Q3      │   t-test    │   0.001    │   *** Yes   │   │
│  │ Q2 vs Q3      │   t-test    │   0.045    │    * Yes    │   │
│  └───────────────┴─────────────┴────────────┴─────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   OVERLAY COMPARISON                     │   │
│  │  Sales ▲                                                 │   │
│  │    │     ╭──────────────────────── Q3 (Green)           │   │
│  │    │   ╭─┴──────────────────────── Q2 (Orange)          │   │
│  │    │ ╭─┴────────────────────────── Q1 (Blue)            │   │
│  │    │╱                                                    │   │
│  │    └─────────────────────────────────────▶ Time         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 DIFFERENCE ANALYSIS                      │   │
│  │                                                          │   │
│  │   Q1 → Q2 Changes:                                       │   │
│  │   ┌────────────────────────────────────────────┐        │   │
│  │   │ ████████████████████░░░░░░░░░░░░░░░░░░░░░░│ +58%   │   │
│  │   │ ░░░░░░░░░░░░░░░░░░░░████████████░░░░░░░░░░│ -32%   │   │
│  │   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████░│  10%   │   │
│  │   └────────────────────────────────────────────┘        │   │
│  │   🟢 Positive: 58%  🔴 Negative: 32%  ⚪ No Change: 10%  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  CORRELATION COMPARISON                  │   │
│  │                                                          │   │
│  │  Dataset A                    Dataset B                  │   │
│  │  ┌─────────────────┐         ┌─────────────────┐        │   │
│  │  │ Correlation: 0.85│         │ Correlation: 0.72│        │   │
│  │  │   (Strong +)    │         │   (Moderate +)  │        │   │
│  │  └─────────────────┘         └─────────────────┘        │   │
│  │                                                          │   │
│  │  Difference: -0.13 (Correlation weakened)               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 비교 모드별 레포트 구성

| 비교 모드 | 포함 섹션 |
|----------|----------|
| **OVERLAY** | 오버레이 차트, 통합 통계 테이블, 범례 |
| **SIDE_BY_SIDE** | 병렬 차트, 개별 통계, 비교 하이라이트 |
| **DIFFERENCE** | 차이 차트, 변화량 분석, 증감 지표 |

### 4.3 통계 검정 결과 표시

```
┌─────────────────────────────────────────────────────────────────┐
│                    STATISTICAL TEST RESULTS                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Test: Independent Samples t-test                               │
│  ───────────────────────────────                                │
│  Comparing: Dataset A (Sales Q1) vs Dataset B (Sales Q2)        │
│  Variable: Revenue                                              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Results                                                  │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ Test Statistic (t)  :  3.245                            │   │
│  │ Degrees of Freedom  :  248                              │   │
│  │ p-value             :  0.0013  ***                      │   │
│  │ Effect Size (d)     :  0.72  (Medium-Large)             │   │
│  │ 95% CI              :  [1,234 , 5,678]                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Interpretation:                                                │
│  ─────────────────                                              │
│  The difference between Dataset A and Dataset B is              │
│  statistically significant (p < 0.01). The effect size          │
│  indicates a medium-to-large practical significance.            │
│                                                                 │
│  Significance Levels:                                           │
│    *   p < 0.05                                                 │
│    **  p < 0.01                                                 │
│    *** p < 0.001                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 사용자 인터페이스

### 5.1 레포트 생성 다이얼로그

```
┌─────────────────────────────────────────────────────────────────┐
│                    Generate Report                         [X]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Report Title: [Sales Analysis Report 2024          ]          │
│  Subtitle:     [Q1-Q3 Performance Comparison        ]          │
│  Author:       [Data Analytics Team                 ]          │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│  Output Format:                                                 │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│  │  HTML  │ │  PDF   │ │  DOCX  │ │  PPTX  │ │  JSON  │       │
│  │   ✓    │ │        │ │        │ │        │ │        │       │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│  Include Sections:                                              │
│  ☑ Executive Summary                                            │
│  ☑ Data Overview                                                │
│  ☑ Statistical Summary                                          │
│  ☑ Visualizations                                               │
│  ☑ Comparison Analysis (멀티데이터 활성화 시)                    │
│  ☑ Data Tables                                                  │
│  ☐ Appendix (Methodology)                                       │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│  Options:                                                       │
│  Theme:      [● Light  ○ Dark  ○ Auto]                         │
│  Page Size:  [A4           ▼]                                  │
│  Charts:     [● Static  ○ Interactive (HTML only)]             │
│  Tables:     [Top 100 rows ▼]                                  │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│  Template:                                                      │
│  [Default                              ▼] [Manage Templates]   │
│                                                                 │
│  ─────────────────────────────────────────────────────────     │
│  Output Path:                                                   │
│  [/home/user/reports/sales_report.html     ] [Browse...]       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                       Preview                            │   │
│  │  ┌───────────────────────────────────────────────────┐  │   │
│  │  │                                                   │  │   │
│  │  │           [Report Preview Thumbnail]              │  │   │
│  │  │                                                   │  │   │
│  │  └───────────────────────────────────────────────────┘  │   │
│  │  Estimated: 15 pages, ~2.5 MB                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                              [Cancel]  [Preview]  [Generate]   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 템플릿 관리자

```
┌─────────────────────────────────────────────────────────────────┐
│                    Template Manager                        [X]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Templates:                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ★ Default                                    [Edit]     │   │
│  │   Standard report layout                     [Delete]   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │   Corporate                                  [Edit]     │   │
│  │   Company branding with logo                 [Delete]   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │   Minimal                                    [Edit]     │   │
│  │   Clean, simple layout                       [Delete]   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │   Executive Brief                            [Edit]     │   │
│  │   Summary-focused, 1-2 pages                 [Delete]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [+ New Template]  [Import...]  [Export...]                    │
│                                                                 │
│                                              [Close]           │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 메뉴 통합

```
File
├── New
├── Open
├── Save
├── ─────────────
├── Export
│   ├── Export Data...           Ctrl+E
│   ├── Export Chart...          Ctrl+Shift+E
│   └── ─────────────
│       Generate Report...       Ctrl+R      ← 새로 추가
│       Quick Report (HTML)      Ctrl+Shift+R
│       Quick Report (PDF)       Ctrl+Alt+R
├── ─────────────
└── Exit

Tools
├── ...
├── ─────────────
├── Report Templates...                       ← 새로 추가
└── ...
```

### 5.4 툴바 버튼

```
┌─────────────────────────────────────────────────────────────────┐
│ [📂] [💾] [↩️] [↪️] │ [📊] [📈] [🔍] │ [📋 Report ▼]          │
│                                        │                        │
│                                        ├── Generate Report...   │
│                                        ├── Quick HTML           │
│                                        ├── Quick PDF            │
│                                        └── Quick PPTX           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 데이터 모델

### 6.1 Core Classes

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class ReportFormat(Enum):
    """레포트 출력 형식"""
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    JSON = "json"
    MARKDOWN = "markdown"


class ReportTheme(Enum):
    """레포트 테마"""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"
    CORPORATE = "corporate"


class PageSize(Enum):
    """페이지 크기"""
    A4 = "a4"
    LETTER = "letter"
    LEGAL = "legal"
    A3 = "a3"


class ChartImageFormat(Enum):
    """차트 이미지 형식"""
    PNG = "png"
    SVG = "svg"
    EMBEDDED = "embedded"  # Base64 embedded


@dataclass
class ReportMetadata:
    """레포트 메타데이터"""
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0"
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    logo_path: Optional[str] = None


@dataclass
class ReportSection:
    """레포트 섹션"""
    id: str
    title: str
    enabled: bool = True
    content: Optional[Any] = None
    order: int = 0


@dataclass
class ReportOptions:
    """레포트 생성 옵션"""
    format: ReportFormat = ReportFormat.HTML
    theme: ReportTheme = ReportTheme.LIGHT
    page_size: PageSize = PageSize.A4
    orientation: str = "portrait"  # portrait | landscape

    # 섹션 포함 여부
    include_executive_summary: bool = True
    include_data_overview: bool = True
    include_statistics: bool = True
    include_visualizations: bool = True
    include_comparison: bool = True  # 멀티데이터 시
    include_tables: bool = True
    include_appendix: bool = False

    # 차트 옵션
    chart_format: ChartImageFormat = ChartImageFormat.PNG
    interactive_charts: bool = False  # HTML만
    chart_dpi: int = 150

    # 테이블 옵션
    table_max_rows: int = 100
    include_raw_data: bool = False

    # 템플릿
    template_id: Optional[str] = None


@dataclass
class DatasetSummary:
    """데이터셋 요약 정보"""
    id: str
    name: str
    file_path: Optional[str]
    row_count: int
    column_count: int
    columns: List[str]
    date_range: Optional[Dict[str, str]] = None
    memory_bytes: int = 0
    color: str = "#1f77b4"


@dataclass
class StatisticalSummary:
    """통계 요약"""
    column: str
    count: int
    sum: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None


@dataclass
class ComparisonResult:
    """비교 분석 결과"""
    dataset_a: str
    dataset_b: str
    test_type: str
    test_statistic: float
    p_value: float
    effect_size: Optional[float] = None
    significant: bool = False
    significance_level: str = ""  # "", "*", "**", "***"
    interpretation: str = ""


@dataclass
class ChartData:
    """차트 데이터"""
    chart_type: str
    title: str
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    group_column: Optional[str] = None
    data: Optional[Any] = None
    image_bytes: Optional[bytes] = None
    image_base64: Optional[str] = None


@dataclass
class ReportData:
    """레포트 전체 데이터"""
    metadata: ReportMetadata
    datasets: List[DatasetSummary]
    statistics: Dict[str, List[StatisticalSummary]]
    comparisons: Optional[List[ComparisonResult]] = None
    charts: List[ChartData] = field(default_factory=list)
    tables: Dict[str, Any] = field(default_factory=dict)
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ReportTemplate:
    """레포트 템플릿"""
    id: str
    name: str
    description: str
    author: str
    created_at: datetime

    # 스타일
    primary_color: str = "#1f77b4"
    secondary_color: str = "#ff7f0e"
    font_family: str = "Arial"

    # 레이아웃
    header_html: Optional[str] = None
    footer_html: Optional[str] = None
    css_styles: Optional[str] = None

    # 기본 옵션
    default_options: Optional[ReportOptions] = None
```

### 6.2 Generator Interface

```python
from abc import ABC, abstractmethod
from typing import Union
from pathlib import Path


class ReportGenerator(ABC):
    """레포트 생성기 기본 클래스"""

    @abstractmethod
    def generate(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """레포트 생성"""
        pass

    @abstractmethod
    def save(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Union[str, Path]
    ) -> Path:
        """레포트 파일 저장"""
        pass

    def preview(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """미리보기 생성 (썸네일)"""
        return self.generate(report_data, options)


class ReportManager:
    """레포트 관리자"""

    def __init__(self):
        self.generators: Dict[ReportFormat, ReportGenerator] = {}
        self.templates: Dict[str, ReportTemplate] = {}

    def register_generator(
        self,
        format: ReportFormat,
        generator: ReportGenerator
    ):
        """생성기 등록"""
        self.generators[format] = generator

    def generate_report(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Optional[Union[str, Path]] = None
    ) -> Union[bytes, Path]:
        """레포트 생성"""
        generator = self.generators.get(options.format)
        if not generator:
            raise ValueError(f"Unsupported format: {options.format}")

        if output_path:
            return generator.save(report_data, options, output_path)
        return generator.generate(report_data, options)

    def add_template(self, template: ReportTemplate):
        """템플릿 추가"""
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[ReportTemplate]:
        """템플릿 조회"""
        return self.templates.get(template_id)
```

---

## 7. 기술 스택

### 7.1 의존성 추가

```python
# requirements.txt 추가 항목
# Report Generation
Jinja2>=3.1.0           # HTML 템플릿 엔진
weasyprint>=60.0        # HTML → PDF 변환
python-docx>=1.1.0      # Word 문서 생성
python-pptx>=0.6.23     # PowerPoint 생성
plotly>=5.18.0          # Interactive charts (기존)
kaleido>=0.2.1          # Plotly static export
Pillow>=10.0.0          # 이미지 처리 (기존)
```

### 7.2 선택적 의존성

```python
# PDF 렌더링 대안
reportlab>=4.0.0        # Pure Python PDF (WeasyPrint 대안)
fpdf2>=2.7.0            # Lightweight PDF

# 고급 기능
openpyxl>=3.1.0         # Excel 생성 (기존)
markdown>=3.5.0         # Markdown 처리
```

---

## 8. 구현 로드맵

### Phase 1: Core Infrastructure (핵심 인프라)
- [ ] ReportData 데이터 모델 구현
- [ ] ReportGenerator 기본 인터페이스
- [ ] ReportManager 구현
- [ ] 기본 템플릿 시스템

### Phase 2: HTML Report (HTML 레포트)
- [ ] Jinja2 템플릿 생성
- [ ] CSS 스타일링 (Light/Dark)
- [ ] 차트 이미지 임베딩
- [ ] Interactive 차트 옵션 (Plotly)
- [ ] 반응형 레이아웃

### Phase 3: PDF Report (PDF 레포트)
- [ ] WeasyPrint 통합
- [ ] 페이지 레이아웃
- [ ] 헤더/푸터
- [ ] 목차 생성
- [ ] 한글 폰트 지원

### Phase 4: Word Report (Word 레포트)
- [ ] python-docx 통합
- [ ] 스타일 시스템
- [ ] 테이블 생성
- [ ] 차트 이미지 삽입
- [ ] 목차 자동 생성

### Phase 5: PowerPoint Report (PPT 레포트)
- [ ] python-pptx 통합
- [ ] 슬라이드 레이아웃
- [ ] 차트 슬라이드
- [ ] 요약 슬라이드
- [ ] 마스터 슬라이드 지원

### Phase 6: Multi-Data Comparison (멀티데이터 비교)
- [ ] 비교 섹션 템플릿
- [ ] 통계 검정 결과 포맷팅
- [ ] 오버레이 차트 생성
- [ ] 차이 분석 시각화
- [ ] 병렬 비교 레이아웃

### Phase 7: UI Integration (UI 통합)
- [ ] ReportDialog 구현
- [ ] 템플릿 매니저 다이얼로그
- [ ] 미리보기 기능
- [ ] 진행률 표시
- [ ] 메뉴/툴바 통합

### Phase 8: Advanced Features (고급 기능)
- [ ] 커스텀 템플릿 에디터
- [ ] 브랜딩 (로고, 색상)
- [ ] 스케줄된 레포트 생성
- [ ] 이메일 전송 통합
- [ ] CLI 명령어 추가

---

## 9. 성능 목표

| 항목 | 목표 |
|------|------|
| HTML 생성 (1M rows) | < 10초 |
| PDF 생성 (1M rows) | < 30초 |
| DOCX 생성 (1M rows) | < 20초 |
| PPTX 생성 (1M rows) | < 25초 |
| 메모리 사용량 | < 500MB 추가 |
| 차트 이미지 생성 | < 2초/차트 |

---

## 10. 테스트 계획

### 10.1 유닛 테스트
- ReportData 모델 생성/직렬화
- 각 Generator별 출력 검증
- 템플릿 렌더링

### 10.2 통합 테스트
- 전체 레포트 생성 파이프라인
- UI 다이얼로그 동작
- 파일 저장/로드

### 10.3 성능 테스트
- 대용량 데이터 레포트 생성
- 메모리 사용량 모니터링
- 생성 시간 측정

---

## 11. 예제 시나리오

### 시나리오 1: 단일 데이터 분석 레포트
```
사용자: 매출 데이터(1M rows) 분석 후 PDF 레포트 생성
결과:
- 10페이지 PDF
- Executive Summary
- 월별 매출 트렌드 차트
- 지역별 매출 분포 파이차트
- 상위 100개 거래 테이블
- 통계 요약
```

### 시나리오 2: 멀티데이터 비교 레포트
```
사용자: Q1 vs Q2 vs Q3 매출 비교 PowerPoint 생성
결과:
- 15 슬라이드 PPTX
- 타이틀 슬라이드
- 데이터셋 개요 슬라이드
- 오버레이 트렌드 차트
- 병렬 비교 차트
- 통계 검정 결과 (t-test, p-values)
- 차이 분석 슬라이드
- 결론 슬라이드
```

### 시나리오 3: 자동화된 일일 레포트
```
CLI: dgs report sales.csv --format pdf --output daily_report.pdf --template corporate
결과:
- 커맨드라인에서 레포트 자동 생성
- 기업 템플릿 적용
- 지정 경로에 저장
```

---

## 12. 제약사항 및 고려사항

### 12.1 기술적 제약
- WeasyPrint는 시스템 라이브러리(Cairo, Pango) 필요
- 대용량 데이터 레포트 시 메모리 관리 필요
- 한글 폰트 시스템 의존성

### 12.2 대안
- PDF: ReportLab (순수 Python, 의존성 적음)
- 한글: NanumGothic 폰트 번들링

### 12.3 보안 고려
- 사용자 입력 HTML 이스케이프
- 파일 경로 검증
- 템플릿 샌드박싱

---

## 13. 성공 지표

| 지표 | 목표 |
|------|------|
| 레포트 생성 성공률 | > 99% |
| 평균 생성 시간 | < 15초 |
| 사용자 만족도 | > 4.5/5 |
| 형식별 사용률 | 측정 및 분석 |
| 템플릿 사용률 | > 30% |
