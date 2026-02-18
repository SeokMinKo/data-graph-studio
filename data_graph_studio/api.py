"""
Data Graph Studio Python API
프로그래매틱하게 그래프 생성

Usage:
    from data_graph_studio import DataGraphStudio
    
    dgs = DataGraphStudio()
    dgs.load("data.csv")
    dgs.plot(x="Time", y=["Value1", "Value2"])
    dgs.save("chart.png")
"""
import os
import io
from pathlib import Path
from typing import Optional, List, Union, Dict, Any
import polars as pl


class DataGraphStudio:
    """Data Graph Studio Python API"""
    
    def __init__(self):
        self._df: Optional[pl.DataFrame] = None
        self._x_column: Optional[str] = None
        self._y_columns: List[str] = []
        self._chart_type: str = 'line'
        self._title: str = ''
        self._config: Dict[str, Any] = {}
        self._filters: List[str] = []
    
    # ==================== Data Loading ====================
    
    def load(self, path: str, **kwargs) -> 'DataGraphStudio':
        """
        파일에서 데이터 로드
        
        Args:
            path: 파일 경로 (CSV, Excel, Parquet, JSON)
            **kwargs: Polars read 함수에 전달할 추가 인자
        
        Returns:
            self (chaining 지원)
        """
        ext = Path(path).suffix.lower()
        
        if ext == '.csv':
            self._df = pl.read_csv(path, infer_schema_length=10000, **kwargs)
        elif ext == '.tsv':
            self._df = pl.read_csv(path, separator='\t', **kwargs)
        elif ext in ['.xlsx', '.xls']:
            self._df = pl.read_excel(path, **kwargs)
        elif ext == '.parquet':
            self._df = pl.read_parquet(path, **kwargs)
        elif ext == '.json':
            self._df = pl.read_json(path, **kwargs)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
        
        return self
    
    def load_dataframe(self, df) -> 'DataGraphStudio':
        """
        pandas DataFrame에서 로드
        
        Args:
            df: pandas DataFrame
        
        Returns:
            self
        """
        self._df = pl.from_pandas(df)
        return self
    
    def load_polars(self, df: pl.DataFrame) -> 'DataGraphStudio':
        """
        Polars DataFrame에서 로드
        
        Args:
            df: Polars DataFrame
        
        Returns:
            self
        """
        self._df = df
        return self
    
    def load_dict(self, data: Dict[str, list]) -> 'DataGraphStudio':
        """
        딕셔너리에서 로드
        
        Args:
            data: 컬럼명 -> 값 리스트 딕셔너리
        
        Returns:
            self
        """
        self._df = pl.DataFrame(data)
        return self
    
    def load_csv_string(self, csv_text: str, **kwargs) -> 'DataGraphStudio':
        """
        CSV 문자열에서 로드
        
        Args:
            csv_text: CSV 형식 문자열
        
        Returns:
            self
        """
        self._df = pl.read_csv(io.StringIO(csv_text), **kwargs)
        return self
    
    # ==================== Data Operations ====================
    
    def filter(self, expr: str) -> 'DataGraphStudio':
        """
        데이터 필터링
        
        Args:
            expr: 필터 표현식 (예: "Value > 100", "Category == 'A'")
        
        Returns:
            self
        """
        self._filters.append(expr)
        return self
    
    def select(self, columns: List[str]) -> 'DataGraphStudio':
        """
        컬럼 선택
        
        Args:
            columns: 선택할 컬럼 목록
        
        Returns:
            self
        """
        if self._df is not None:
            self._df = self._df.select(columns)
        return self
    
    def sort(self, column: str, descending: bool = False) -> 'DataGraphStudio':
        """
        정렬
        
        Args:
            column: 정렬 기준 컬럼
            descending: 내림차순 여부
        
        Returns:
            self
        """
        if self._df is not None:
            self._df = self._df.sort(column, descending=descending)
        return self
    
    def head(self, n: int = 10) -> 'DataGraphStudio':
        """처음 n개 행"""
        if self._df is not None:
            self._df = self._df.head(n)
        return self
    
    def tail(self, n: int = 10) -> 'DataGraphStudio':
        """마지막 n개 행"""
        if self._df is not None:
            self._df = self._df.tail(n)
        return self
    
    # ==================== Plotting ====================
    
    def plot(self, x: str = None, y: Union[str, List[str]] = None, 
             chart: str = None) -> 'DataGraphStudio':
        """
        그래프 설정
        
        Args:
            x: X축 컬럼명
            y: Y축 컬럼명 (단일 또는 리스트)
            chart: 차트 타입 (line, bar, scatter, pie, area, histogram)
        
        Returns:
            self
        """
        if x:
            self._x_column = x
        elif self._df is not None and not self._x_column:
            self._x_column = self._df.columns[0]
        
        if y:
            if isinstance(y, str):
                self._y_columns = [y]
            else:
                self._y_columns = list(y)
        elif self._df is not None and not self._y_columns:
            # 숫자 컬럼 자동 선택
            numeric_cols = [c for c in self._df.columns 
                          if self._df[c].dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32]]
            self._y_columns = numeric_cols[:3] if numeric_cols else self._df.columns[1:2]
        
        if chart:
            self._chart_type = chart
        
        return self
    
    def set_title(self, title: str) -> 'DataGraphStudio':
        """차트 제목 설정"""
        self._title = title
        return self
    
    def set_axis_labels(self, x: str = None, y: str = None) -> 'DataGraphStudio':
        """축 레이블 설정"""
        if x:
            self._config['x_label'] = x
        if y:
            self._config['y_label'] = y
        return self
    
    def set_legend(self, show: bool = True, position: str = 'right') -> 'DataGraphStudio':
        """범례 설정"""
        self._config['show_legend'] = show
        self._config['legend_position'] = position
        return self
    
    def set_grid(self, show: bool = True) -> 'DataGraphStudio':
        """그리드 설정"""
        self._config['show_grid'] = show
        return self
    
    def set_colors(self, colors: List[str]) -> 'DataGraphStudio':
        """색상 설정"""
        self._config['colors'] = colors
        return self
    
    def set_size(self, width: int, height: int) -> 'DataGraphStudio':
        """이미지 크기 설정"""
        self._config['width'] = width
        self._config['height'] = height
        return self
    
    # ==================== Output ====================
    
    def save(self, path: str, format: str = None, dpi: int = 100) -> None:
        """
        이미지 파일로 저장
        
        Args:
            path: 출력 파일 경로
            format: 포맷 (자동 감지 또는 png, jpg, svg, pdf)
            dpi: DPI 설정
        """
        if self._df is None:
            raise ValueError("No data loaded. Call load() first.")
        
        # 필터 적용
        df = self._apply_filters()
        
        # 렌더링
        self._render_and_save(df, path, dpi)
    
    def to_image(self, format: str = 'png', dpi: int = 100) -> bytes:
        """
        이미지 바이트로 반환
        
        Args:
            format: 이미지 포맷
            dpi: DPI 설정
        
        Returns:
            이미지 바이트
        """
        import tempfile
        
        if self._df is None:
            raise ValueError("No data loaded")
        
        with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as f:
            temp_path = f.name
        
        try:
            self.save(temp_path, format=format, dpi=dpi)
            with open(temp_path, 'rb') as f:
                return f.read()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def show(self) -> None:
        """
        Jupyter/IPython에서 인라인 표시
        """
        try:
            from IPython.display import display, Image
            img_bytes = self.to_image('png')
            display(Image(data=img_bytes))
        except ImportError:
            print("IPython not available. Use save() instead.")
    
    def to_html(self) -> str:
        """HTML로 변환 — HTMLReportGenerator 사용"""
        from data_graph_studio.report.html_generator import HTMLReportGenerator
        from data_graph_studio.core.report import (
            ReportData, ReportOptions, ReportMetadata, DatasetSummary,
        )

        if self._df is None:
            raise ValueError("No data loaded")

        metadata = ReportMetadata(title=self._title or "Data Graph Studio Report")
        dataset = DatasetSummary(
            id="api",
            name=self._title or "Dataset",
            row_count=len(self._df),
            column_count=len(self._df.columns),
            column_types={c: str(self._df[c].dtype) for c in self._df.columns},
            memory_bytes=self._df.estimated_size(),
            color="#4A90D9",
        )
        report_data = ReportData(metadata=metadata, datasets=[dataset])
        options = ReportOptions()

        generator = HTMLReportGenerator()
        html_bytes = generator.generate(report_data, options)
        return html_bytes.decode("utf-8")
    
    # ==================== Data Access ====================
    
    @property
    def data(self) -> Optional[pl.DataFrame]:
        """현재 데이터프레임 반환"""
        return self._df
    
    @property
    def columns(self) -> List[str]:
        """컬럼 목록"""
        return self._df.columns if self._df is not None else []
    
    @property
    def shape(self) -> tuple:
        """데이터 shape (rows, cols)"""
        if self._df is None:
            return (0, 0)
        return (len(self._df), len(self._df.columns))
    
    def describe(self) -> pl.DataFrame:
        """데이터 요약 통계"""
        if self._df is None:
            raise ValueError("No data loaded")
        return self._df.describe()
    
    def info(self) -> Dict[str, Any]:
        """데이터 정보"""
        if self._df is None:
            return {}
        
        return {
            'rows': len(self._df),
            'columns': len(self._df.columns),
            'column_names': self._df.columns,
            'dtypes': {c: str(self._df[c].dtype) for c in self._df.columns},
            'memory_bytes': self._df.estimated_size(),
        }
    
    # ==================== Static Methods ====================
    
    @staticmethod
    def from_config(config: Dict[str, Any]) -> 'DataGraphStudio':
        """
        설정 딕셔너리에서 생성
        
        Args:
            config: 설정 딕셔너리
                - data: 파일 경로 또는 데이터
                - x: X축 컬럼
                - y: Y축 컬럼
                - chart: 차트 타입
                - title: 제목
                - output: 출력 파일
        
        Returns:
            DataGraphStudio 인스턴스
        """
        dgs = DataGraphStudio()
        
        # 데이터 로드
        data = config.get('data')
        if isinstance(data, str):
            dgs.load(data)
        elif isinstance(data, dict):
            dgs.load_dict(data)
        elif isinstance(data, list):
            # [[x1,y1], [x2,y2], ...] 형식
            if data and isinstance(data[0], list):
                cols = config.get('columns', ['x', 'y'])
                d = {col: [row[i] for row in data] for i, col in enumerate(cols)}
                dgs.load_dict(d)
        
        # 플롯 설정
        dgs.plot(
            x=config.get('x'),
            y=config.get('y'),
            chart=config.get('chart', 'line')
        )
        
        if config.get('title'):
            dgs.set_title(config['title'])
        
        return dgs
    
    @staticmethod
    def quick_plot(data: Union[str, Dict, pl.DataFrame], 
                   x: str = None, y: Union[str, List[str]] = None,
                   chart: str = 'line', output: str = None, 
                   show: bool = False) -> Optional['DataGraphStudio']:
        """
        빠른 플롯 (한 줄)
        
        Args:
            data: 데이터 (파일 경로, 딕셔너리, DataFrame)
            x: X축 컬럼
            y: Y축 컬럼
            chart: 차트 타입
            output: 출력 파일 (None이면 show)
            show: Jupyter에서 표시
        
        Returns:
            DataGraphStudio 인스턴스 (output이 None인 경우)
        """
        dgs = DataGraphStudio()
        
        if isinstance(data, str):
            dgs.load(data)
        elif isinstance(data, dict):
            dgs.load_dict(data)
        elif isinstance(data, pl.DataFrame):
            dgs.load_polars(data)
        else:
            # pandas DataFrame
            dgs.load_dataframe(data)
        
        dgs.plot(x=x, y=y, chart=chart)
        
        if output:
            dgs.save(output)
            return dgs
        elif show:
            dgs.show()
            return dgs
        else:
            return dgs
    
    # ==================== Internal ====================
    
    def _apply_filters(self) -> pl.DataFrame:
        """필터 적용"""
        df = self._df
        
        for expr in self._filters:
            try:
                # 간단한 필터 파싱
                # 예: "Value > 100", "Category == 'A'"
                df = df.filter(pl.sql_expr(expr))
            except:
                pass
        
        return df
    
    def _render_and_save(self, df: pl.DataFrame, path: str, dpi: int):
        """렌더링 및 저장"""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        width = self._config.get('width', 1920)
        height = self._config.get('height', 1080)
        
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi)
        
        x_data = df[self._x_column].to_list() if self._x_column else list(range(len(df)))
        colors = self._config.get('colors')
        
        for i, y_col in enumerate(self._y_columns):
            y_data = df[y_col].to_list()
            color = colors[i] if colors and i < len(colors) else None
            
            if self._chart_type == 'line':
                ax.plot(x_data, y_data, label=y_col, color=color, marker='o', markersize=2)
            elif self._chart_type == 'bar':
                width_bar = 0.8 / len(self._y_columns)
                offset = (i - len(self._y_columns)/2 + 0.5) * width_bar
                x_pos = range(len(x_data))
                ax.bar([p + offset for p in x_pos], y_data, width_bar, 
                      label=y_col, color=color, alpha=0.8)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(x_data)
            elif self._chart_type == 'scatter':
                ax.scatter(x_data, y_data, label=y_col, color=color, alpha=0.7)
            elif self._chart_type == 'area':
                ax.fill_between(range(len(x_data)), y_data, alpha=0.5, 
                               label=y_col, color=color)
                ax.plot(range(len(x_data)), y_data, color=color)
            elif self._chart_type == 'histogram':
                ax.hist(y_data, bins=30, alpha=0.7, label=y_col, color=color)
            elif self._chart_type == 'pie':
                ax.pie(y_data, labels=x_data, autopct='%1.1f%%')
        
        # 스타일링
        if self._title:
            ax.set_title(self._title, fontsize=14, fontweight='bold')
        
        ax.set_xlabel(self._config.get('x_label', self._x_column or ''))
        ax.set_ylabel(self._config.get('y_label', ', '.join(self._y_columns)))
        
        if self._config.get('show_legend', True) and self._chart_type != 'pie':
            ax.legend(loc=self._config.get('legend_position', 'best'))
        
        if self._config.get('show_grid', True) and self._chart_type != 'pie':
            ax.grid(True, alpha=0.3)
        
        # X축 라벨 회전
        if len(x_data) > 10:
            plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(path, dpi=dpi, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close()


# 편의 함수
def plot(data, x=None, y=None, chart='line', output=None, show=False):
    """Quick plot function"""
    return DataGraphStudio.quick_plot(data, x, y, chart, output, show)


def load(path: str) -> DataGraphStudio:
    """Quick load function"""
    return DataGraphStudio().load(path)
