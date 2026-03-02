"""
Data Graph Studio REST API Server
HTTP로 그래프 생성

Usage:
    dgs server --port 8080

    curl -X POST http://localhost:8080/api/v1/plot \
        -F "data=@data.csv" \
        -F "x=Time" -F "y=Value" \
        -o chart.png
"""
import os
import io
import json
import logging
import tempfile
import time
from collections import OrderedDict
from typing import Optional, List
import polars as pl

logger = logging.getLogger(__name__)

# Upload size limit: 500 MB
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
API_AUTH_HEADER = "x-dgs-api-token"

try:
    from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def _get_api_version() -> str:
    """API 버전을 패키지 버전에서 가져온다."""
    try:
        from . import __version__
        return __version__
    except Exception:
        return "0.0.0"


if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Data Graph Studio API",
        description="REST API for creating charts from data",
        version=_get_api_version(),
    )

    # ==================== Models ====================

    class PlotConfig(BaseModel):
        x: Optional[str] = None
        y: Optional[List[str]] = None
        chart: str = "line"
        title: Optional[str] = None
        width: int = 1920
        height: int = 1080
        dpi: int = 100

    class DataInfo(BaseModel):
        rows: int
        columns: int
        column_names: List[str]
        dtypes: dict
        memory_bytes: int

    class StatusResponse(BaseModel):
        status: str
        version: str
        endpoints: List[str]

    # ==================== Storage ====================

    # 임시 데이터 저장 (세션별, LRU eviction + TTL)
    _MAX_DATA_STORE_ENTRIES = 50
    _DATA_STORE_TTL_SECONDS = 3600  # 1 hour
    _data_store: OrderedDict = OrderedDict()
    _data_store_timestamps: dict = {}

    def _evict_data_store() -> None:
        """Max entries 초과 또는 TTL 만료 세션을 제거한다."""
        now = time.time()
        # TTL eviction
        expired = [
            sid for sid, ts in _data_store_timestamps.items()
            if now - ts > _DATA_STORE_TTL_SECONDS
        ]
        for sid in expired:
            _data_store.pop(sid, None)
            _data_store_timestamps.pop(sid, None)
        # Count eviction (LRU)
        while len(_data_store) > _MAX_DATA_STORE_ENTRIES:
            evicted_sid, _ = _data_store.popitem(last=False)
            _data_store_timestamps.pop(evicted_sid, None)

    async def _read_upload_with_limit(upload: UploadFile) -> bytes:
        """업로드 파일을 크기 제한과 함께 읽는다."""
        content = await upload.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"Upload too large ({len(content)} bytes). "
                f"Maximum: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            )
        return content

    def _require_api_token(request: Request) -> None:
        """선택적 API 토큰 인증 (DGS_API_TOKEN 설정 시 필수)."""
        expected = os.environ.get("DGS_API_TOKEN", "").strip()
        if not expected:
            return

        provided = request.headers.get(API_AUTH_HEADER, "").strip()
        if provided != expected:
            raise HTTPException(401, "Unauthorized: invalid or missing API token")

    # ==================== Endpoints ====================

    @app.get("/")
    def root():
        """API 정보"""
        return {
            "name": "Data Graph Studio API",
            "version": _get_api_version(),
            "docs": "/docs",
        }

    @app.get("/api/v1/status")
    def get_status() -> StatusResponse:
        """서버 상태"""
        return StatusResponse(
            status="running",
            version=_get_api_version(),
            endpoints=[
                "/api/v1/status",
                "/api/v1/plot",
                "/api/v1/data/upload",
                "/api/v1/data/info",
                "/api/v1/convert",
            ]
        )

    @app.post("/api/v1/plot")
    async def create_plot(
        request: Request,
        data: Optional[UploadFile] = File(None),
        config: Optional[str] = Form(None),
        x: Optional[str] = Form(None),
        y: Optional[str] = Form(None),
        chart: str = Form("line"),
        title: Optional[str] = Form(None),
        width: int = Form(1920),
        height: int = Form(1080),
        format: str = Form("png"),
    ):
        """
        그래프 생성

        - data: 데이터 파일 (CSV, Excel, Parquet)
        - config: JSON 설정 (선택)
        - x: X축 컬럼
        - y: Y축 컬럼 (쉼표로 구분)
        - chart: 차트 타입
        - format: 출력 포맷 (png, jpg, svg, pdf)
        """
        from .api import DataGraphStudio

        _require_api_token(request)

        # 설정 파싱
        plot_config = {}
        if config:
            try:
                plot_config = json.loads(config)
            except json.JSONDecodeError:
                raise HTTPException(400, "Invalid JSON config")

        # 데이터 로드
        if data:
            content = await _read_upload_with_limit(data)
            filename = data.filename or "data.csv"
            ext = os.path.splitext(filename)[1].lower()

            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(content)
                temp_path = f.name

            try:
                dgs = DataGraphStudio().load(temp_path)
            finally:
                os.remove(temp_path)
        else:
            raise HTTPException(400, "No data provided")

        # 플롯 설정
        x_col = x or plot_config.get('x')
        y_cols = (y.split(',') if y else None) or plot_config.get('y')
        chart_type = plot_config.get('chart', chart)

        dgs.plot(x=x_col, y=y_cols, chart=chart_type)

        if title or plot_config.get('title'):
            dgs.set_title(title or plot_config.get('title'))

        dgs.set_size(
            plot_config.get('width', width),
            plot_config.get('height', height)
        )

        # 이미지 생성
        img_bytes = dgs.to_image(format=format)

        # 응답
        media_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'svg': 'image/svg+xml',
            'pdf': 'application/pdf',
        }

        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type=media_types.get(format, 'image/png'),
            headers={
                'Content-Disposition': f'attachment; filename=chart.{format}'
            }
        )

    @app.post("/api/v1/plot/json")
    async def create_plot_json(request: Request, config: PlotConfig, data: dict):
        """
        JSON 데이터로 그래프 생성

        Body:
        {
            "config": {"x": "time", "y": ["value"], "chart": "line"},
            "data": {"time": [1,2,3], "value": [10,20,15]}
        }
        """
        from .api import DataGraphStudio

        _require_api_token(request)

        dgs = DataGraphStudio()
        dgs.load_dict(data)
        dgs.plot(x=config.x, y=config.y, chart=config.chart)

        if config.title:
            dgs.set_title(config.title)

        dgs.set_size(config.width, config.height)

        img_bytes = dgs.to_image('png', dpi=config.dpi)

        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type='image/png'
        )

    @app.post("/api/v1/data/upload")
    async def upload_data(
        request: Request,
        file: UploadFile = File(...),
        session_id: Optional[str] = Form(None)
    ):
        """데이터 파일 업로드"""
        _require_api_token(request)
        content = await _read_upload_with_limit(file)
        filename = file.filename or "data.csv"
        ext = os.path.splitext(filename)[1].lower()

        # 파싱
        try:
            if ext == '.csv':
                df = pl.read_csv(io.BytesIO(content))
            elif ext == '.tsv':
                df = pl.read_csv(io.BytesIO(content), separator='\t')
            elif ext in ['.xlsx', '.xls']:
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                    f.write(content)
                    temp_path = f.name
                df = pl.read_excel(temp_path)
                os.remove(temp_path)
            elif ext == '.parquet':
                df = pl.read_parquet(io.BytesIO(content))
            elif ext == '.json':
                df = pl.read_json(io.BytesIO(content))
            else:
                raise HTTPException(400, f"Unsupported format: {ext}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Parse error: {e}")

        # 저장 (LRU eviction)
        import uuid
        sid = session_id or str(uuid.uuid4())[:8]
        _data_store[sid] = df
        _data_store.move_to_end(sid)
        _data_store_timestamps[sid] = time.time()
        _evict_data_store()

        return {
            "session_id": sid,
            "rows": len(df),
            "columns": df.columns,
        }

    @app.get("/api/v1/data/info/{session_id}")
    def get_data_info(session_id: str, request: Request) -> DataInfo:
        """업로드된 데이터 정보"""
        _require_api_token(request)
        if session_id not in _data_store:
            raise HTTPException(404, "Session not found")

        df = _data_store[session_id]

        return DataInfo(
            rows=len(df),
            columns=len(df.columns),
            column_names=df.columns,
            dtypes={c: str(df[c].dtype) for c in df.columns},
            memory_bytes=df.estimated_size(),
        )

    @app.post("/api/v1/data/{session_id}/plot")
    async def plot_uploaded_data(
        session_id: str,
        request: Request,
        x: Optional[str] = Form(None),
        y: Optional[str] = Form(None),
        chart: str = Form("line"),
        title: Optional[str] = Form(None),
        format: str = Form("png"),
    ):
        """업로드된 데이터로 그래프 생성"""
        _require_api_token(request)
        if session_id not in _data_store:
            raise HTTPException(404, "Session not found")

        from .api import DataGraphStudio

        df = _data_store[session_id]
        dgs = DataGraphStudio()
        dgs.load_polars(df)

        y_cols = y.split(',') if y else None
        dgs.plot(x=x, y=y_cols, chart=chart)

        if title:
            dgs.set_title(title)

        img_bytes = dgs.to_image(format=format)

        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type=f'image/{format}'
        )

    @app.post("/api/v1/convert")
    async def convert_file(
        request: Request,
        file: UploadFile = File(...),
        output_format: str = Form("csv"),
    ):
        """파일 포맷 변환"""
        _require_api_token(request)
        content = await _read_upload_with_limit(file)
        filename = file.filename or "data.csv"
        in_ext = os.path.splitext(filename)[1].lower()

        # 로드
        try:
            if in_ext == '.csv':
                df = pl.read_csv(io.BytesIO(content))
            elif in_ext == '.tsv':
                df = pl.read_csv(io.BytesIO(content), separator='\t')
            elif in_ext == '.parquet':
                df = pl.read_parquet(io.BytesIO(content))
            elif in_ext == '.json':
                df = pl.read_json(io.BytesIO(content))
            else:
                raise HTTPException(400, f"Unsupported input format: {in_ext}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Parse error: {e}")

        # 변환
        output = io.BytesIO()

        if output_format == 'csv':
            df.write_csv(output)
            media_type = 'text/csv'
        elif output_format == 'tsv':
            df.write_csv(output, separator='\t')
            media_type = 'text/tab-separated-values'
        elif output_format == 'json':
            df.write_json(output)
            media_type = 'application/json'
        elif output_format == 'parquet':
            # parquet는 바이트 버퍼에 직접 쓸 수 없어서 임시 파일 사용
            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
                df.write_parquet(f.name)
                with open(f.name, 'rb') as pf:
                    output.write(pf.read())
                os.remove(f.name)
            media_type = 'application/octet-stream'
        else:
            raise HTTPException(400, f"Unsupported output format: {output_format}")

        output.seek(0)

        return StreamingResponse(
            output,
            media_type=media_type,
            headers={
                'Content-Disposition': f'attachment; filename=data.{output_format}'
            }
        )

    @app.delete("/api/v1/data/{session_id}")
    def delete_data(session_id: str, request: Request):
        """업로드된 데이터 삭제"""
        _require_api_token(request)
        if session_id in _data_store:
            del _data_store[session_id]
            _data_store_timestamps.pop(session_id, None)
            return {"status": "deleted"}
        raise HTTPException(404, "Session not found")


def run_server(host: str = "127.0.0.1", port: int = 8080):
    """서버 실행"""
    if not FASTAPI_AVAILABLE:
        print("FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")
        return

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
