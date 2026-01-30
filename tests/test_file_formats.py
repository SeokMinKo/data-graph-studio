"""
Test cases for extended file format and delimiter support
"""

import pytest
import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from data_graph_studio.core.data_engine import DataEngine, FileType, DelimiterType
except ImportError:
    from data_graph_studio.core.data_engine import DataEngine, FileType, DelimiterType


class TestFileTypeDetection:
    """파일 형식 자동 감지 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
    
    def test_detect_csv(self):
        assert self.engine.detect_file_type("data.csv") == FileType.CSV
    
    def test_detect_tsv(self):
        assert self.engine.detect_file_type("data.tsv") == FileType.TSV
    
    def test_detect_txt(self):
        assert self.engine.detect_file_type("data.txt") == FileType.TXT
    
    def test_detect_log(self):
        assert self.engine.detect_file_type("data.log") == FileType.TXT
    
    def test_detect_dat(self):
        assert self.engine.detect_file_type("data.dat") == FileType.TXT
    
    def test_detect_etl(self):
        assert self.engine.detect_file_type("data.etl") == FileType.ETL
    
    def test_detect_excel_xlsx(self):
        assert self.engine.detect_file_type("data.xlsx") == FileType.EXCEL
    
    def test_detect_excel_xls(self):
        assert self.engine.detect_file_type("data.xls") == FileType.EXCEL
    
    def test_detect_parquet(self):
        assert self.engine.detect_file_type("data.parquet") == FileType.PARQUET
    
    def test_detect_json(self):
        assert self.engine.detect_file_type("data.json") == FileType.JSON
    
    def test_detect_unknown_defaults_to_txt(self):
        assert self.engine.detect_file_type("data.xyz") == FileType.TXT


class TestDelimiterDetection:
    """구분자 자동 감지 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
        self.test_dir = Path(__file__).parent.parent / "test_data"
    
    def test_detect_comma(self):
        path = self.test_dir / "test_comma.csv"
        if path.exists():
            delimiter = self.engine.detect_delimiter(str(path))
            assert delimiter == ','
    
    def test_detect_tab(self):
        path = self.test_dir / "test_tab.tsv"
        if path.exists():
            delimiter = self.engine.detect_delimiter(str(path))
            assert delimiter == '\t'
    
    def test_detect_semicolon(self):
        path = self.test_dir / "test_semicolon.txt"
        if path.exists():
            delimiter = self.engine.detect_delimiter(str(path))
            assert delimiter == ';'
    
    def test_detect_pipe(self):
        path = self.test_dir / "test_pipe.txt"
        if path.exists():
            delimiter = self.engine.detect_delimiter(str(path))
            assert delimiter == '|'


class TestCSVLoading:
    """CSV 파일 로딩 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
        self.test_dir = Path(__file__).parent.parent / "test_data"
    
    def test_load_csv_comma(self):
        path = self.test_dir / "test_comma.csv"
        if path.exists():
            success = self.engine.load_file(str(path))
            assert success
            assert self.engine.row_count == 3
            assert 'name' in self.engine.columns
            assert 'age' in self.engine.columns
            assert 'score' in self.engine.columns
    
    def test_load_tsv(self):
        path = self.test_dir / "test_tab.tsv"
        if path.exists():
            success = self.engine.load_file(str(path))
            assert success
            assert self.engine.row_count == 3


class TestTextLoading:
    """텍스트 파일 로딩 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
        self.test_dir = Path(__file__).parent.parent / "test_data"
    
    def test_load_space_delimited(self):
        path = self.test_dir / "test_space.txt"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.SPACE
            )
            assert success
            assert self.engine.row_count == 3
    
    def test_load_multispace(self):
        """연속 공백 처리 테스트"""
        path = self.test_dir / "test_multispace.log"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.SPACE
            )
            assert success
            assert self.engine.row_count == 3
    
    def test_load_semicolon_delimited(self):
        path = self.test_dir / "test_semicolon.txt"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.SEMICOLON
            )
            assert success
            assert self.engine.row_count == 3
    
    def test_load_pipe_delimited(self):
        path = self.test_dir / "test_pipe.txt"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.PIPE
            )
            assert success
            assert self.engine.row_count == 3


class TestAdvancedOptions:
    """고급 옵션 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
        self.test_dir = Path(__file__).parent.parent / "test_data"
    
    def test_skip_rows(self):
        """상단 행 스킵 테스트"""
        path = self.test_dir / "test_skip_rows.txt"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                skip_rows=2,
                delimiter_type=DelimiterType.COMMA
            )
            assert success
            assert self.engine.row_count == 3
            assert 'name' in self.engine.columns
    
    def test_comment_char(self):
        """주석 문자 처리 테스트"""
        path = self.test_dir / "test_comment.dat"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                comment_char='#',
                delimiter_type=DelimiterType.COMMA
            )
            assert success
            # 주석 제외하고 3개 데이터 행
            assert self.engine.row_count == 3


class TestRegexDelimiter:
    """Regex 구분자 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
    
    def test_regex_multiple_spaces(self):
        """여러 공백을 regex로 처리"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("name   age   score\n")
            f.write("Alice  25    85.5\n")
            f.write("Bob    30    92.0\n")
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(
                tmp_path,
                file_type=FileType.TXT,
                delimiter_type=DelimiterType.REGEX,
                regex_pattern=r'\s+'
            )
            assert success
            assert self.engine.row_count == 2
        finally:
            os.unlink(tmp_path)
    
    def test_regex_custom_pattern(self):
        """커스텀 regex 패턴"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("name::age::score\n")
            f.write("Alice::25::85.5\n")
            f.write("Bob::30::92.0\n")
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(
                tmp_path,
                file_type=FileType.TXT,
                delimiter_type=DelimiterType.REGEX,
                regex_pattern=r'::'
            )
            assert success
            assert self.engine.row_count == 2
            assert 'name' in self.engine.columns
        finally:
            os.unlink(tmp_path)


class TestAutoDelimiter:
    """자동 구분자 감지 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
        self.test_dir = Path(__file__).parent.parent / "test_data"
    
    def test_auto_detect_comma(self):
        path = self.test_dir / "test_comma.csv"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.AUTO
            )
            assert success
            assert self.engine.row_count == 3
    
    def test_auto_detect_semicolon(self):
        path = self.test_dir / "test_semicolon.txt"
        if path.exists():
            success = self.engine.load_file(
                str(path),
                delimiter_type=DelimiterType.AUTO
            )
            assert success
            assert self.engine.row_count == 3


class TestDataTypes:
    """데이터 타입 자동 변환 테스트"""
    
    def setup_method(self):
        self.engine = DataEngine()
    
    def test_numeric_conversion(self):
        """숫자 타입 자동 변환"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("id value\n")
            f.write("1 100\n")
            f.write("2 200\n")
            f.write("3 300\n")
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(
                tmp_path,
                file_type=FileType.TXT,
                delimiter_type=DelimiterType.SPACE
            )
            assert success
            
            # 숫자로 변환되었는지 확인
            dtypes = self.engine.dtypes
            assert 'Int' in dtypes.get('id', '') or 'int' in dtypes.get('id', '').lower()
        finally:
            os.unlink(tmp_path)


class TestETLFiles:
    """ETL 파일 로딩 테스트"""

    def setup_method(self):
        self.engine = DataEngine()

    def test_binary_etl_detection(self):
        """바이너리 ETL 파일 감지 테스트"""
        import platform

        # 바이너리 ETL 파일 시뮬레이션 (null 바이트 포함)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.etl', delete=False) as f:
            # WPR ETL 파일과 유사한 바이너리 헤더 (null 바이트 포함)
            binary_header = bytes([
                0x42, 0x00, 0x55, 0x00, 0x46, 0x00, 0x46, 0x00,  # B.U.F.F. (UTF-16)
                0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            ] * 20)  # 반복하여 512바이트 이상
            f.write(binary_header)
            tmp_path = f.name

        try:
            # 바이너리 ETL은 Windows가 아닌 환경에서 에러 발생해야 함
            success = self.engine.load_file(tmp_path, file_type=FileType.ETL)

            if platform.system() != 'Windows':
                # Linux/Mac에서는 실패하고 적절한 에러 메시지
                assert not success
                assert "ETL" in self.engine.progress.error_message
            # Windows에서는 tracerpt가 없으면 실패
        finally:
            os.unlink(tmp_path)

    def test_text_etl_loading(self):
        """텍스트 ETL 파일 (변환된 파일) 로딩 테스트"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.etl', delete=False) as f:
            # 이미 CSV로 변환된 ETL 파일 형태
            f.write("EventName,TimeStamp,ProcessId,ThreadId\n")
            f.write("DiskRead,1234567890,100,200\n")
            f.write("DiskWrite,1234567891,100,201\n")
            f.write("FileCreate,1234567892,101,300\n")
            tmp_path = f.name

        try:
            success = self.engine.load_file(tmp_path, file_type=FileType.ETL)
            assert success
            assert self.engine.row_count == 3
            assert 'EventName' in self.engine.columns
            assert 'TimeStamp' in self.engine.columns
        finally:
            os.unlink(tmp_path)

    def test_binary_vs_text_detection(self):
        """바이너리 vs 텍스트 구분 테스트"""
        # 텍스트 파일 (null 바이트 없음)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.etl', delete=False) as f:
            f.write("col1,col2,col3\n")
            f.write("a,b,c\n")
            tmp_path_text = f.name

        # 바이너리 파일 (null 바이트 있음)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.etl', delete=False) as f:
            f.write(b'\x00\x01\x02\x03\x04\x05' * 100)
            tmp_path_binary = f.name

        try:
            # 텍스트 ETL은 성공해야 함
            success_text = self.engine.load_file(tmp_path_text, file_type=FileType.ETL)
            assert success_text

            # 바이너리 ETL은 Linux/Mac에서 실패해야 함
            import platform
            self.engine.clear()
            success_binary = self.engine.load_file(tmp_path_binary, file_type=FileType.ETL)

            if platform.system() != 'Windows':
                assert not success_binary
        finally:
            os.unlink(tmp_path_text)
            os.unlink(tmp_path_binary)


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def setup_method(self):
        self.engine = DataEngine()
    
    def test_empty_file(self):
        """빈 파일 처리"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(tmp_path, file_type=FileType.TXT)
            # 빈 파일은 성공하지만 데이터 없음
            assert self.engine.row_count == 0
        finally:
            os.unlink(tmp_path)
    
    def test_single_column(self):
        """단일 컬럼 파일"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("values\n")
            f.write("100\n")
            f.write("200\n")
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(tmp_path, file_type=FileType.TXT)
            assert success
            assert self.engine.column_count == 1
        finally:
            os.unlink(tmp_path)
    
    def test_inconsistent_columns(self):
        """컬럼 수 불일치 처리"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("a,b,c\n")
            f.write("1,2\n")  # 컬럼 부족
            f.write("1,2,3,4\n")  # 컬럼 초과
            tmp_path = f.name
        
        try:
            success = self.engine.load_file(
                tmp_path,
                file_type=FileType.TXT,
                delimiter_type=DelimiterType.COMMA
            )
            assert success
            assert self.engine.column_count == 3  # 헤더 기준
        finally:
            os.unlink(tmp_path)
    
    def test_file_not_found(self):
        """존재하지 않는 파일"""
        success = self.engine.load_file("/nonexistent/path/file.csv")
        assert not success
        assert self.engine.progress.status == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
