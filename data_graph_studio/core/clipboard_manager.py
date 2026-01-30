"""
Clipboard Manager - 복사/붙여넣기 기능
Excel, Google Sheets, 텍스트 데이터와 연동
"""
import io
import re
from typing import Optional, Tuple, List
import polars as pl
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QImage


class ClipboardManager:
    """클립보드 데이터 관리"""
    
    @staticmethod
    def get_clipboard() -> QMimeData:
        """클립보드 데이터 가져오기"""
        clipboard = QApplication.clipboard()
        return clipboard.mimeData()
    
    @staticmethod
    def has_table_data() -> bool:
        """테이블 형식 데이터 존재 여부"""
        mime = ClipboardManager.get_clipboard()
        
        # HTML (Excel, Google Sheets)
        if mime.hasHtml():
            html = mime.html()
            if '<table' in html.lower() or '<tr' in html.lower():
                return True
        
        # 텍스트 (TSV, CSV)
        if mime.hasText():
            text = mime.text()
            # 탭이나 쉼표로 구분된 데이터 확인
            lines = text.strip().split('\n')
            if len(lines) >= 1:
                first_line = lines[0]
                if '\t' in first_line or ',' in first_line:
                    return True
        
        return False
    
    @staticmethod
    def paste_as_dataframe() -> Tuple[Optional[pl.DataFrame], str]:
        """
        클립보드에서 DataFrame으로 변환
        Returns: (DataFrame or None, status_message)
        """
        mime = ClipboardManager.get_clipboard()
        
        # 1. HTML 테이블 (Excel, Google Sheets에서 복사)
        if mime.hasHtml():
            html = mime.html()
            df = ClipboardManager._parse_html_table(html)
            if df is not None:
                return df, f"Pasted {len(df)} rows from HTML table"
        
        # 2. 텍스트 (TSV/CSV)
        if mime.hasText():
            text = mime.text()
            df = ClipboardManager._parse_text_data(text)
            if df is not None:
                return df, f"Pasted {len(df)} rows from text"
        
        return None, "No valid table data in clipboard"
    
    @staticmethod
    def _parse_html_table(html: str) -> Optional[pl.DataFrame]:
        """HTML 테이블 파싱"""
        try:
            # 간단한 HTML 테이블 파싱
            # <tr>...</tr> 추출
            row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
            cell_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.IGNORECASE | re.DOTALL)
            
            rows = row_pattern.findall(html)
            if not rows:
                return None
            
            data = []
            for row in rows:
                cells = cell_pattern.findall(row)
                # HTML 태그 제거
                clean_cells = [re.sub(r'<[^>]+>', '', cell).strip() for cell in cells]
                if clean_cells:
                    data.append(clean_cells)
            
            if len(data) < 1:
                return None
            
            # 첫 행을 헤더로 사용
            headers = data[0]
            rows_data = data[1:] if len(data) > 1 else []
            
            # 헤더가 비어있으면 자동 생성
            if not any(headers):
                headers = [f'Column_{i+1}' for i in range(len(headers))]
            
            # 중복 헤더 처리
            seen = {}
            unique_headers = []
            for h in headers:
                if h in seen:
                    seen[h] += 1
                    unique_headers.append(f"{h}_{seen[h]}")
                else:
                    seen[h] = 0
                    unique_headers.append(h)
            
            # DataFrame 생성
            if rows_data:
                # 컬럼 수 맞추기
                max_cols = max(len(row) for row in rows_data)
                max_cols = max(max_cols, len(unique_headers))
                
                # 헤더 패딩
                while len(unique_headers) < max_cols:
                    unique_headers.append(f'Column_{len(unique_headers)+1}')
                
                # 데이터 패딩
                padded_rows = []
                for row in rows_data:
                    padded = row + [''] * (max_cols - len(row))
                    padded_rows.append(padded[:max_cols])
                
                df = pl.DataFrame(
                    {h: [row[i] for row in padded_rows] for i, h in enumerate(unique_headers)}
                )
            else:
                # 헤더만 있는 경우
                df = pl.DataFrame({h: [] for h in unique_headers})
            
            # 숫자 컬럼 자동 변환
            df = ClipboardManager._auto_convert_types(df)
            
            return df
            
        except Exception as e:
            print(f"HTML parse error: {e}")
            return None
    
    @staticmethod
    def _parse_text_data(text: str) -> Optional[pl.DataFrame]:
        """텍스트 데이터 파싱 (TSV, CSV)"""
        try:
            text = text.strip()
            if not text:
                return None
            
            lines = text.split('\n')
            if not lines:
                return None
            
            # 구분자 감지
            first_line = lines[0]
            if '\t' in first_line:
                delimiter = '\t'
            elif ',' in first_line:
                delimiter = ','
            elif ';' in first_line:
                delimiter = ';'
            else:
                # 공백으로 구분된 경우
                delimiter = None
            
            if delimiter:
                # CSV/TSV 파싱
                csv_text = text
                df = pl.read_csv(io.StringIO(csv_text), separator=delimiter, 
                                infer_schema_length=1000, ignore_errors=True)
            else:
                # 공백 구분
                rows = [line.split() for line in lines]
                if len(rows) > 1:
                    headers = rows[0]
                    data_rows = rows[1:]
                    
                    # 컬럼 수 맞추기
                    max_cols = max(len(r) for r in data_rows) if data_rows else len(headers)
                    while len(headers) < max_cols:
                        headers.append(f'Column_{len(headers)+1}')
                    
                    df = pl.DataFrame({
                        h: [r[i] if i < len(r) else '' for r in data_rows]
                        for i, h in enumerate(headers)
                    })
                else:
                    return None
            
            # 숫자 변환
            df = ClipboardManager._auto_convert_types(df)
            
            return df
            
        except Exception as e:
            print(f"Text parse error: {e}")
            return None
    
    @staticmethod
    def _auto_convert_types(df: pl.DataFrame) -> pl.DataFrame:
        """자동 타입 변환"""
        for col in df.columns:
            try:
                # 숫자 변환 시도
                numeric = df[col].cast(pl.Float64, strict=False)
                if numeric.null_count() < len(df) * 0.5:  # 50% 이상 변환 성공
                    # 정수인지 확인
                    if (numeric == numeric.floor()).all():
                        df = df.with_columns(numeric.cast(pl.Int64).alias(col))
                    else:
                        df = df.with_columns(numeric.alias(col))
            except:
                pass
        return df
    
    @staticmethod
    def copy_dataframe(df: pl.DataFrame, include_header: bool = True) -> str:
        """DataFrame을 클립보드에 복사 (TSV 형식)"""
        clipboard = QApplication.clipboard()
        
        # TSV 형식으로 변환
        output = io.StringIO()
        df.write_csv(output, separator='\t', include_header=include_header)
        text = output.getvalue()
        
        clipboard.setText(text)
        return f"Copied {len(df)} rows to clipboard"
    
    @staticmethod
    def copy_image(image: QImage) -> str:
        """이미지를 클립보드에 복사"""
        clipboard = QApplication.clipboard()
        clipboard.setImage(image)
        return "Image copied to clipboard"
    
    @staticmethod
    def copy_text(text: str) -> str:
        """텍스트를 클립보드에 복사"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        return "Text copied to clipboard"


class DragDropHandler:
    """드래그 앤 드롭 처리"""
    
    SUPPORTED_EXTENSIONS = {
        '.csv', '.tsv', '.txt',
        '.xlsx', '.xls',
        '.parquet',
        '.json',
        '.dgs',  # 프로젝트 파일
        '.dgsp',  # 프로필 파일
    }
    
    @staticmethod
    def get_supported_files(urls: list) -> List[str]:
        """드롭된 URL에서 지원 파일 추출"""
        files = []
        for url in urls:
            if url.isLocalFile():
                path = url.toLocalFile()
                ext = '.' + path.split('.')[-1].lower() if '.' in path else ''
                if ext in DragDropHandler.SUPPORTED_EXTENSIONS:
                    files.append(path)
        return files
    
    @staticmethod
    def is_supported_file(path: str) -> bool:
        """지원하는 파일인지 확인"""
        ext = '.' + path.split('.')[-1].lower() if '.' in path else ''
        return ext in DragDropHandler.SUPPORTED_EXTENSIONS
    
    @staticmethod
    def get_file_type(path: str) -> str:
        """파일 타입 반환"""
        ext = '.' + path.split('.')[-1].lower() if '.' in path else ''
        
        if ext in {'.csv', '.tsv', '.txt'}:
            return 'data'
        elif ext in {'.xlsx', '.xls'}:
            return 'excel'
        elif ext == '.parquet':
            return 'parquet'
        elif ext == '.json':
            return 'json'
        elif ext == '.dgs':
            return 'project'
        elif ext == '.dgsp':
            return 'profile'
        else:
            return 'unknown'
