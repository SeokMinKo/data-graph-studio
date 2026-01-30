"""
Data Graph Studio CLI
커맨드 라인에서 그래프 생성

Usage:
    dgs plot data.csv -x Time -y Value -o output.png
    dgs plot data.csv --chart bar -x Category -y Sales
    dgs info data.csv
    dgs convert data.csv -o data.parquet
    dgs server --port 8080
"""
import argparse
import sys
import os
import json
from pathlib import Path
from typing import Optional, List


def create_parser():
    """CLI 파서 생성"""
    parser = argparse.ArgumentParser(
        prog='dgs',
        description='Data Graph Studio - Command Line Interface',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dgs plot data.csv -x Time -y Value -o chart.png
  dgs plot data.csv --chart bar -x Category -y "Sales,Profit"
  dgs plot data.csv --profile my_profile -o report.png
  dgs info data.csv
  dgs convert data.xlsx -o data.csv
  dgs batch ./data/ -o ./output/ --chart line
  dgs server --port 8080
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # ===== plot command =====
    plot_parser = subparsers.add_parser('plot', help='Create a chart from data')
    plot_parser.add_argument('input', help='Input data file (CSV, Excel, Parquet, JSON)')
    plot_parser.add_argument('-x', '--x-column', help='X-axis column name')
    plot_parser.add_argument('-y', '--y-columns', help='Y-axis column names (comma-separated)')
    plot_parser.add_argument('-c', '--chart', default='line',
                            choices=['line', 'bar', 'scatter', 'pie', 'area', 'histogram'],
                            help='Chart type (default: line)')
    plot_parser.add_argument('-o', '--output', help='Output file (png, jpg, svg, pdf)')
    plot_parser.add_argument('--width', type=int, default=1920, help='Image width (default: 1920)')
    plot_parser.add_argument('--height', type=int, default=1080, help='Image height (default: 1080)')
    plot_parser.add_argument('--title', help='Chart title')
    plot_parser.add_argument('--profile', help='Apply saved profile')
    plot_parser.add_argument('--config', help='JSON config file')
    plot_parser.add_argument('--headless', action='store_true', help='Run without GUI')
    plot_parser.add_argument('--dpi', type=int, default=100, help='DPI for output (default: 100)')
    
    # ===== info command =====
    info_parser = subparsers.add_parser('info', help='Show data file information')
    info_parser.add_argument('input', help='Input data file')
    info_parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    # ===== convert command =====
    convert_parser = subparsers.add_parser('convert', help='Convert data file format')
    convert_parser.add_argument('input', help='Input file')
    convert_parser.add_argument('-o', '--output', required=True, help='Output file')
    convert_parser.add_argument('--sheet', help='Sheet name (for Excel files)')
    
    # ===== batch command =====
    batch_parser = subparsers.add_parser('batch', help='Process multiple files')
    batch_parser.add_argument('input_dir', help='Input directory')
    batch_parser.add_argument('-o', '--output-dir', required=True, help='Output directory')
    batch_parser.add_argument('--config', help='JSON config file')
    batch_parser.add_argument('-c', '--chart', default='line', help='Chart type')
    batch_parser.add_argument('-x', '--x-column', help='X-axis column')
    batch_parser.add_argument('-y', '--y-columns', help='Y-axis columns')
    batch_parser.add_argument('--format', default='png', choices=['png', 'jpg', 'svg', 'pdf'],
                             help='Output format (default: png)')
    
    # ===== server command =====
    server_parser = subparsers.add_parser('server', help='Start REST API server')
    server_parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    server_parser.add_argument('--host', default='127.0.0.1', help='Server host (default: 127.0.0.1)')
    
    # ===== watch command =====
    watch_parser = subparsers.add_parser('watch', help='Watch file and auto-update chart')
    watch_parser.add_argument('input', help='Input file to watch')
    watch_parser.add_argument('-o', '--output', required=True, help='Output image file')
    watch_parser.add_argument('--interval', type=float, default=5, help='Check interval in seconds')
    watch_parser.add_argument('-x', '--x-column', help='X-axis column')
    watch_parser.add_argument('-y', '--y-columns', help='Y-axis columns')
    watch_parser.add_argument('-c', '--chart', default='line', help='Chart type')
    
    return parser


def cmd_plot(args):
    """plot 명령 실행"""
    import polars as pl
    
    # 입력 파일 확인
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1
    
    # 설정 파일 로드
    config = {}
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # 데이터 로드
    ext = Path(args.input).suffix.lower()
    try:
        if ext == '.csv':
            df = pl.read_csv(args.input, infer_schema_length=10000)
        elif ext == '.tsv':
            df = pl.read_csv(args.input, separator='\t', infer_schema_length=10000)
        elif ext in ['.xlsx', '.xls']:
            df = pl.read_excel(args.input)
        elif ext == '.parquet':
            df = pl.read_parquet(args.input)
        elif ext == '.json':
            df = pl.read_json(args.input)
        else:
            print(f"Error: Unsupported format: {ext}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error loading file: {e}", file=sys.stderr)
        return 1
    
    print(f"Loaded: {len(df)} rows, {len(df.columns)} columns")
    
    # 컬럼 설정
    x_col = args.x_column or config.get('x') or df.columns[0]
    y_cols_str = args.y_columns or config.get('y')
    
    if y_cols_str:
        y_cols = [c.strip() for c in y_cols_str.split(',')]
    else:
        # 숫자 컬럼 자동 선택
        numeric_cols = [c for c in df.columns if df[c].dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Int16, pl.Int8]]
        y_cols = numeric_cols[:3] if numeric_cols else [df.columns[1] if len(df.columns) > 1 else df.columns[0]]
    
    chart_type = args.chart or config.get('chart', 'line')
    title = args.title or config.get('title', '')
    
    print(f"Chart: {chart_type}, X: {x_col}, Y: {y_cols}")
    
    # 출력 파일
    output_file = args.output or config.get('output')
    if not output_file:
        output_file = Path(args.input).stem + '_chart.png'
    
    # Headless 렌더링
    try:
        from .headless_renderer import HeadlessRenderer
        
        renderer = HeadlessRenderer(width=args.width, height=args.height, dpi=args.dpi)
        renderer.render(
            df=df,
            x_column=x_col,
            y_columns=y_cols,
            chart_type=chart_type,
            title=title,
            output_path=output_file
        )
        print(f"Saved: {output_file}")
        return 0
        
    except ImportError:
        # Fallback: matplotlib 사용
        return _plot_with_matplotlib(df, x_col, y_cols, chart_type, title, output_file, args)


def _plot_with_matplotlib(df, x_col, y_cols, chart_type, title, output_file, args):
    """Matplotlib로 플롯 (fallback)"""
    try:
        import matplotlib
        matplotlib.use('Agg')  # Headless
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(args.width/100, args.height/100), dpi=args.dpi)
        
        x_data = df[x_col].to_list()
        
        for y_col in y_cols:
            y_data = df[y_col].to_list()
            
            if chart_type == 'line':
                ax.plot(x_data, y_data, label=y_col, marker='o', markersize=3)
            elif chart_type == 'bar':
                ax.bar(x_data, y_data, label=y_col, alpha=0.7)
            elif chart_type == 'scatter':
                ax.scatter(x_data, y_data, label=y_col, alpha=0.7)
            elif chart_type == 'area':
                ax.fill_between(range(len(x_data)), y_data, alpha=0.5, label=y_col)
                ax.plot(range(len(x_data)), y_data)
            elif chart_type == 'histogram':
                ax.hist(y_data, bins=30, alpha=0.7, label=y_col)
        
        ax.set_xlabel(x_col)
        ax.set_ylabel(', '.join(y_cols))
        if title:
            ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # X축 라벨 회전 (많을 경우)
        if len(x_data) > 10:
            plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=args.dpi, bbox_inches='tight')
        plt.close()
        
        print(f"Saved: {output_file}")
        return 0
        
    except Exception as e:
        print(f"Error creating chart: {e}", file=sys.stderr)
        return 1


def cmd_info(args):
    """info 명령 실행"""
    import polars as pl
    
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1
    
    ext = Path(args.input).suffix.lower()
    
    try:
        if ext == '.csv':
            df = pl.read_csv(args.input, infer_schema_length=10000)
        elif ext == '.tsv':
            df = pl.read_csv(args.input, separator='\t')
        elif ext in ['.xlsx', '.xls']:
            df = pl.read_excel(args.input)
        elif ext == '.parquet':
            df = pl.read_parquet(args.input)
        elif ext == '.json':
            df = pl.read_json(args.input)
        else:
            print(f"Error: Unsupported format: {ext}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    info = {
        'file': args.input,
        'rows': len(df),
        'columns': len(df.columns),
        'column_info': [
            {
                'name': col,
                'dtype': str(df[col].dtype),
                'null_count': df[col].null_count(),
                'unique_count': df[col].n_unique(),
            }
            for col in df.columns
        ],
        'memory_bytes': df.estimated_size(),
    }
    
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(f"File: {info['file']}")
        print(f"Rows: {info['rows']:,}")
        print(f"Columns: {info['columns']}")
        print(f"Memory: {info['memory_bytes'] / 1024 / 1024:.2f} MB")
        print("\nColumns:")
        for col_info in info['column_info']:
            print(f"  {col_info['name']}: {col_info['dtype']} "
                  f"(nulls: {col_info['null_count']}, unique: {col_info['unique_count']})")
    
    return 0


def cmd_convert(args):
    """convert 명령 실행"""
    import polars as pl
    
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1
    
    in_ext = Path(args.input).suffix.lower()
    out_ext = Path(args.output).suffix.lower()
    
    # 로드
    try:
        if in_ext == '.csv':
            df = pl.read_csv(args.input)
        elif in_ext == '.tsv':
            df = pl.read_csv(args.input, separator='\t')
        elif in_ext in ['.xlsx', '.xls']:
            df = pl.read_excel(args.input, sheet_name=args.sheet)
        elif in_ext == '.parquet':
            df = pl.read_parquet(args.input)
        elif in_ext == '.json':
            df = pl.read_json(args.input)
        else:
            print(f"Error: Unsupported input format: {in_ext}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error loading: {e}", file=sys.stderr)
        return 1
    
    # 저장
    try:
        if out_ext == '.csv':
            df.write_csv(args.output)
        elif out_ext == '.tsv':
            df.write_csv(args.output, separator='\t')
        elif out_ext == '.parquet':
            df.write_parquet(args.output)
        elif out_ext == '.json':
            df.write_json(args.output)
        elif out_ext in ['.xlsx', '.xls']:
            df.write_excel(args.output)
        else:
            print(f"Error: Unsupported output format: {out_ext}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error saving: {e}", file=sys.stderr)
        return 1
    
    print(f"Converted: {args.input} -> {args.output}")
    print(f"Rows: {len(df):,}")
    return 0


def cmd_batch(args):
    """batch 명령 실행"""
    import polars as pl
    from pathlib import Path
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}", file=sys.stderr)
        return 1
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 설정 로드
    config = {}
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # 지원 파일 찾기
    patterns = ['*.csv', '*.tsv', '*.xlsx', '*.parquet', '*.json']
    files = []
    for pattern in patterns:
        files.extend(input_dir.glob(pattern))
    
    if not files:
        print(f"No data files found in {input_dir}")
        return 1
    
    print(f"Processing {len(files)} files...")
    
    success = 0
    failed = 0
    
    for file_path in files:
        output_file = output_dir / f"{file_path.stem}.{args.format}"
        
        # plot 인자 생성
        plot_args = argparse.Namespace(
            input=str(file_path),
            x_column=args.x_column or config.get('x'),
            y_columns=args.y_columns or config.get('y'),
            chart=args.chart or config.get('chart', 'line'),
            output=str(output_file),
            width=config.get('width', 1920),
            height=config.get('height', 1080),
            title=config.get('title', file_path.stem),
            profile=None,
            config=None,
            headless=True,
            dpi=config.get('dpi', 100),
        )
        
        result = cmd_plot(plot_args)
        if result == 0:
            success += 1
        else:
            failed += 1
    
    print(f"\nDone: {success} success, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_watch(args):
    """watch 명령 실행"""
    import time
    
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1
    
    print(f"Watching: {args.input}")
    print(f"Output: {args.output}")
    print(f"Interval: {args.interval}s")
    print("Press Ctrl+C to stop\n")
    
    last_mtime = 0
    
    try:
        while True:
            mtime = os.path.getmtime(args.input)
            
            if mtime > last_mtime:
                last_mtime = mtime
                print(f"[{time.strftime('%H:%M:%S')}] File changed, updating...")
                
                plot_args = argparse.Namespace(
                    input=args.input,
                    x_column=args.x_column,
                    y_columns=args.y_columns,
                    chart=args.chart,
                    output=args.output,
                    width=1920,
                    height=1080,
                    title=None,
                    profile=None,
                    config=None,
                    headless=True,
                    dpi=100,
                )
                
                cmd_plot(plot_args)
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def cmd_server(args):
    """server 명령 실행"""
    try:
        from .api_server import run_server
        print(f"Starting API server on {args.host}:{args.port}")
        run_server(host=args.host, port=args.port)
    except ImportError:
        print("API server module not found. Install with: pip install fastapi uvicorn")
        return 1
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1


def main():
    """메인 진입점"""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    commands = {
        'plot': cmd_plot,
        'info': cmd_info,
        'convert': cmd_convert,
        'batch': cmd_batch,
        'watch': cmd_watch,
        'server': cmd_server,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
