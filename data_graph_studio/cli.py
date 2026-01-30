#!/usr/bin/env python3
"""
Data Graph Studio - Command Line Interface

Usage:
    dgs <command> [options]

Commands:
    info        Show file information and statistics
    stats       Calculate statistics for columns
    filter      Filter data and export
    export      Export data to different formats
    graph       Generate graph image (headless)
    query       Run Polars SQL query
    serve       Start API server for integration

Examples:
    dgs info data.csv
    dgs stats data.csv --columns Sales,Quantity
    dgs filter data.csv --where "Sales > 100" --output filtered.csv
    dgs graph data.csv --x Date --y Sales --type line --output chart.png
    dgs export data.csv --format parquet --output data.parquet
"""

import sys
import os
import json
from pathlib import Path
from typing import Optional, List

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import click
import polars as pl

# Add src to path for imports
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core.data_engine import DataEngine, FileType
from core.expression_engine import ExpressionEngine


# ==================== Helpers ====================

def get_engine() -> DataEngine:
    """Get a DataEngine instance"""
    return DataEngine()


def load_file(engine: DataEngine, path: str, **kwargs) -> bool:
    """Load a file into the engine"""
    if not os.path.exists(path):
        click.echo(click.style(f"Error: File not found: {path}", fg='red'), err=True)
        return False
    
    success = engine.load_file(path, **kwargs)
    if not success:
        click.echo(click.style(f"Error: Failed to load file: {engine.progress.error_message}", fg='red'), err=True)
        return False
    
    return True


def format_bytes(size: int) -> str:
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_number(num) -> str:
    """Format number with commas"""
    if num is None:
        return "N/A"
    if isinstance(num, float):
        return f"{num:,.2f}"
    return f"{num:,}"


# ==================== CLI Commands ====================

@click.group()
@click.version_option(version='0.1.0', prog_name='Data Graph Studio')
def cli():
    """Data Graph Studio - Big Data Visualization Tool
    
    A powerful CLI for data analysis and visualization.
    """
    pass


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--format', '-f', 'output_format', type=click.Choice(['text', 'json']), default='text',
              help='Output format')
def info(file: str, output_format: str):
    """Show file information and basic statistics
    
    FILE: Path to data file (CSV, Excel, Parquet, JSON)
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    profile = engine.profile
    
    if output_format == 'json':
        result = {
            'file': file,
            'rows': profile.total_rows,
            'columns': profile.total_columns,
            'memory_bytes': profile.memory_bytes,
            'load_time_seconds': profile.load_time_seconds,
            'column_info': [
                {
                    'name': col.name,
                    'dtype': col.dtype,
                    'null_count': col.null_count,
                    'unique_count': col.unique_count,
                    'is_numeric': col.is_numeric,
                }
                for col in profile.columns
            ]
        }
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        # Text format
        click.echo(click.style(f"\n📊 File: {file}", fg='cyan', bold=True))
        click.echo(f"   Rows: {profile.total_rows:,}")
        click.echo(f"   Columns: {profile.total_columns}")
        click.echo(f"   Memory: {format_bytes(profile.memory_bytes)}")
        click.echo(f"   Load time: {profile.load_time_seconds:.2f}s")
        
        click.echo(click.style("\n📋 Columns:", fg='yellow'))
        for col in profile.columns:
            icon = "🔢" if col.is_numeric else "📝" if col.dtype == 'Utf8' else "📅" if col.is_temporal else "📦"
            null_info = f" ({col.null_count} nulls)" if col.null_count > 0 else ""
            click.echo(f"   {icon} {col.name}: {col.dtype}{null_info}")


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--columns', '-c', help='Comma-separated column names (default: all numeric)')
@click.option('--format', '-f', 'output_format', type=click.Choice(['text', 'json', 'csv']), default='text')
def stats(file: str, columns: Optional[str], output_format: str):
    """Calculate statistics for columns
    
    FILE: Path to data file
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    # Determine columns
    if columns:
        col_list = [c.strip() for c in columns.split(',')]
    else:
        col_list = None  # Will use all numeric
    
    all_stats = engine.get_all_statistics(col_list)
    
    if output_format == 'json':
        click.echo(json.dumps(all_stats, indent=2, default=str))
    elif output_format == 'csv':
        # CSV header
        click.echo("column,count,mean,std,min,q1,median,q3,max,null_count")
        for col, st in all_stats.items():
            click.echo(f"{col},{st.get('count','')},{st.get('mean','')},{st.get('std','')},{st.get('min','')},{st.get('q1','')},{st.get('median','')},{st.get('q3','')},{st.get('max','')},{st.get('null_count','')}")
    else:
        click.echo(click.style(f"\n📈 Statistics for {file}", fg='cyan', bold=True))
        
        for col, st in all_stats.items():
            click.echo(click.style(f"\n  {col}:", fg='yellow'))
            click.echo(f"    Count:  {format_number(st.get('count'))}")
            click.echo(f"    Mean:   {format_number(st.get('mean'))}")
            click.echo(f"    Std:    {format_number(st.get('std'))}")
            click.echo(f"    Min:    {format_number(st.get('min'))}")
            click.echo(f"    25%:    {format_number(st.get('q1'))}")
            click.echo(f"    50%:    {format_number(st.get('median'))}")
            click.echo(f"    75%:    {format_number(st.get('q3'))}")
            click.echo(f"    Max:    {format_number(st.get('max'))}")


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--where', '-w', 'condition', help='Filter condition (e.g., "Sales > 100")')
@click.option('--columns', '-c', help='Columns to select (comma-separated)')
@click.option('--limit', '-n', type=int, help='Limit number of rows')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--format', '-f', 'output_format', type=click.Choice(['csv', 'json', 'parquet']), default='csv')
def filter(file: str, condition: Optional[str], columns: Optional[str], 
           limit: Optional[int], output: Optional[str], output_format: str):
    """Filter and export data
    
    FILE: Path to data file
    
    Examples:
        dgs filter data.csv --where "Sales > 100" --output high_sales.csv
        dgs filter data.csv -c "Name,Sales" -n 10
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    df = engine.df
    
    # Apply filter condition using Polars SQL
    if condition:
        try:
            # Use Polars SQL context
            ctx = pl.SQLContext(data=df)
            query = f"SELECT * FROM data WHERE {condition}"
            df = ctx.execute(query).collect()
        except Exception as e:
            click.echo(click.style(f"Error in filter condition: {e}", fg='red'), err=True)
            sys.exit(1)
    
    # Select columns
    if columns:
        col_list = [c.strip() for c in columns.split(',')]
        try:
            df = df.select(col_list)
        except Exception as e:
            click.echo(click.style(f"Error selecting columns: {e}", fg='red'), err=True)
            sys.exit(1)
    
    # Limit
    if limit:
        df = df.head(limit)
    
    # Output
    if output:
        if output_format == 'csv':
            df.write_csv(output)
        elif output_format == 'json':
            df.write_json(output)
        elif output_format == 'parquet':
            df.write_parquet(output)
        
        click.echo(click.style(f"✓ Exported {len(df):,} rows to {output}", fg='green'))
    else:
        # Print to stdout
        click.echo(df)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--output', '-o', required=True, type=click.Path(), help='Output file path')
@click.option('--format', '-f', 'output_format', type=click.Choice(['csv', 'excel', 'parquet', 'json']), 
              help='Output format (auto-detected from extension)')
def export(file: str, output: str, output_format: Optional[str]):
    """Export data to different formats
    
    FILE: Path to input data file
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    # Auto-detect format from extension
    if not output_format:
        ext = Path(output).suffix.lower()
        format_map = {
            '.csv': 'csv',
            '.xlsx': 'excel',
            '.xls': 'excel',
            '.parquet': 'parquet',
            '.pq': 'parquet',
            '.json': 'json',
        }
        output_format = format_map.get(ext, 'csv')
    
    try:
        if output_format == 'csv':
            engine.export_csv(output)
        elif output_format == 'excel':
            engine.export_excel(output)
        elif output_format == 'parquet':
            engine.export_parquet(output)
        elif output_format == 'json':
            engine.df.write_json(output)
        
        click.echo(click.style(f"✓ Exported to {output}", fg='green'))
    except Exception as e:
        click.echo(click.style(f"Error exporting: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--x', '-x', 'x_col', help='X-axis column')
@click.option('--y', '-y', 'y_col', required=True, help='Y-axis column')
@click.option('--group', '-g', 'group_col', help='Group by column')
@click.option('--type', '-t', 'chart_type', type=click.Choice(['line', 'bar', 'scatter', 'area']), default='line')
@click.option('--output', '-o', required=True, type=click.Path(), help='Output image path (PNG)')
@click.option('--width', type=int, default=800, help='Image width')
@click.option('--height', type=int, default=600, help='Image height')
@click.option('--title', help='Chart title')
@click.option('--sample', type=int, help='Sample N rows for large datasets')
def graph(file: str, x_col: Optional[str], y_col: str, group_col: Optional[str],
          chart_type: str, output: str, width: int, height: int, 
          title: Optional[str], sample: Optional[int]):
    """Generate graph image (headless mode)
    
    FILE: Path to data file
    
    Examples:
        dgs graph data.csv --y Sales --output sales.png
        dgs graph data.csv --x Date --y Sales --type line --output trend.png
        dgs graph data.csv --x Category --y Sales --group Region --output grouped.png
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    df = engine.df
    
    # Sample if needed
    if sample and len(df) > sample:
        df = df.sample(n=sample, seed=42)
    
    # Get data
    if x_col:
        x_data = df[x_col].to_numpy()
    else:
        x_data = list(range(len(df)))
    
    y_data = df[y_col].to_numpy()
    
    # Generate plot using matplotlib (headless)
    try:
        import matplotlib
        matplotlib.use('Agg')  # Headless backend
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
        
        colors = ['#6366F1', '#EC4899', '#10B981', '#F59E0B', '#3B82F6',
                  '#EF4444', '#8B5CF6', '#06B6D4', '#84CC16', '#F97316']
        
        if group_col:
            # Grouped plot
            groups = df[group_col].unique().sort().to_list()
            
            for i, group in enumerate(groups):
                mask = (df[group_col] == group).to_numpy()
                color = colors[i % len(colors)]
                
                if chart_type == 'line':
                    ax.plot(np.array(x_data)[mask], y_data[mask], label=str(group), color=color, linewidth=2)
                elif chart_type == 'scatter':
                    ax.scatter(np.array(x_data)[mask], y_data[mask], label=str(group), color=color, alpha=0.7)
                elif chart_type == 'bar':
                    # For bar charts with groups, need different approach
                    ax.bar(np.array(x_data)[mask], y_data[mask], label=str(group), color=color, alpha=0.8)
                elif chart_type == 'area':
                    ax.fill_between(np.array(x_data)[mask], y_data[mask], label=str(group), color=color, alpha=0.3)
                    ax.plot(np.array(x_data)[mask], y_data[mask], color=color, linewidth=1)
            
            ax.legend()
        else:
            # Single series
            color = colors[0]
            
            if chart_type == 'line':
                ax.plot(x_data, y_data, color=color, linewidth=2)
            elif chart_type == 'scatter':
                ax.scatter(x_data, y_data, color=color, alpha=0.7)
            elif chart_type == 'bar':
                ax.bar(x_data, y_data, color=color, alpha=0.8)
            elif chart_type == 'area':
                ax.fill_between(range(len(y_data)), y_data, color=color, alpha=0.3)
                ax.plot(y_data, color=color, linewidth=1)
        
        # Styling
        ax.set_xlabel(x_col or 'Index')
        ax.set_ylabel(y_col)
        ax.set_title(title or f'{y_col} by {x_col or "Index"}')
        ax.grid(True, alpha=0.3)
        
        # Save
        plt.tight_layout()
        plt.savefig(output, dpi=100, bbox_inches='tight')
        plt.close()
        
        click.echo(click.style(f"✓ Graph saved to {output}", fg='green'))
        
    except ImportError:
        click.echo(click.style("Error: matplotlib required for graph generation. Install with: pip install matplotlib", fg='red'), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Error generating graph: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.argument('sql')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--format', '-f', 'output_format', type=click.Choice(['table', 'csv', 'json']), default='table')
def query(file: str, sql: str, output: Optional[str], output_format: str):
    """Run SQL query on data
    
    FILE: Path to data file
    SQL: SQL query (table name is 'data')
    
    Examples:
        dgs query data.csv "SELECT Category, SUM(Sales) FROM data GROUP BY Category"
        dgs query data.csv "SELECT * FROM data WHERE Sales > 100 LIMIT 10"
    """
    engine = get_engine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    try:
        ctx = pl.SQLContext(data=engine.df)
        result = ctx.execute(sql).collect()
        
        if output:
            if output_format == 'csv' or output.endswith('.csv'):
                result.write_csv(output)
            elif output_format == 'json' or output.endswith('.json'):
                result.write_json(output)
            else:
                result.write_csv(output)
            
            click.echo(click.style(f"✓ Query result saved to {output}", fg='green'))
        else:
            if output_format == 'json':
                click.echo(result.write_json())
            elif output_format == 'csv':
                click.echo(result.write_csv())
            else:
                click.echo(result)
                
    except Exception as e:
        click.echo(click.style(f"SQL Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True))
@click.argument('expression')
@click.option('--name', '-n', required=True, help='Name for the new column')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
def calc(file: str, expression: str, name: str, output: Optional[str]):
    """Add calculated column
    
    FILE: Path to data file
    EXPRESSION: Calculation expression (e.g., "Price * Quantity")
    
    Examples:
        dgs calc data.csv "Price * Quantity" --name Total --output with_total.csv
        dgs calc data.csv "ROUND(Sales / 1000, 2)" --name Sales_K
    """
    engine = get_engine()
    expr_engine = ExpressionEngine()
    
    if not load_file(engine, file):
        sys.exit(1)
    
    try:
        df = expr_engine.add_column(engine.df, name, expression)
        
        if output:
            df.write_csv(output)
            click.echo(click.style(f"✓ Added column '{name}' and saved to {output}", fg='green'))
        else:
            click.echo(df)
            
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.option('--port', '-p', type=int, default=8080, help='Server port')
@click.option('--host', '-h', 'host', default='127.0.0.1', help='Server host')
def serve(port: int, host: str):
    """Start HTTP API server for integration
    
    Endpoints:
        POST /load          Load a file
        GET  /info          Get current data info
        GET  /stats         Get statistics
        POST /query         Run SQL query
        POST /filter        Filter data
        GET  /export        Export data
    """
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import json
        import urllib.parse
        
        engine = DataEngine()
        
        class APIHandler(BaseHTTPRequestHandler):
            def _send_json(self, data, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())
            
            def _get_body(self):
                length = int(self.headers.get('Content-Length', 0))
                return json.loads(self.rfile.read(length)) if length else {}
            
            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
            
            def do_GET(self):
                path = urllib.parse.urlparse(self.path).path
                
                if path == '/info':
                    if not engine.is_loaded:
                        self._send_json({'error': 'No data loaded'}, 400)
                        return
                    
                    self._send_json({
                        'rows': engine.row_count,
                        'columns': engine.columns,
                        'dtypes': engine.dtypes,
                    })
                
                elif path == '/stats':
                    if not engine.is_loaded:
                        self._send_json({'error': 'No data loaded'}, 400)
                        return
                    
                    self._send_json(engine.get_all_statistics())
                
                elif path == '/health':
                    self._send_json({'status': 'ok', 'loaded': engine.is_loaded})
                
                else:
                    self._send_json({'error': 'Not found'}, 404)
            
            def do_POST(self):
                path = urllib.parse.urlparse(self.path).path
                body = self._get_body()
                
                if path == '/load':
                    file_path = body.get('path')
                    if not file_path:
                        self._send_json({'error': 'path required'}, 400)
                        return
                    
                    success = engine.load_file(file_path)
                    if success:
                        self._send_json({
                            'success': True,
                            'rows': engine.row_count,
                            'columns': engine.columns,
                        })
                    else:
                        self._send_json({'error': engine.progress.error_message}, 400)
                
                elif path == '/query':
                    sql = body.get('sql')
                    if not sql or not engine.is_loaded:
                        self._send_json({'error': 'sql required and data must be loaded'}, 400)
                        return
                    
                    try:
                        ctx = pl.SQLContext(data=engine.df)
                        result = ctx.execute(sql).collect()
                        self._send_json({
                            'columns': result.columns,
                            'data': result.to_dicts(),
                        })
                    except Exception as e:
                        self._send_json({'error': str(e)}, 400)
                
                elif path == '/filter':
                    condition = body.get('where')
                    columns = body.get('columns')
                    limit = body.get('limit')
                    
                    if not engine.is_loaded:
                        self._send_json({'error': 'No data loaded'}, 400)
                        return
                    
                    df = engine.df
                    
                    if condition:
                        try:
                            ctx = pl.SQLContext(data=df)
                            df = ctx.execute(f"SELECT * FROM data WHERE {condition}").collect()
                        except Exception as e:
                            self._send_json({'error': str(e)}, 400)
                            return
                    
                    if columns:
                        df = df.select(columns)
                    
                    if limit:
                        df = df.head(limit)
                    
                    self._send_json({
                        'columns': df.columns,
                        'data': df.to_dicts(),
                        'rows': len(df),
                    })
                
                else:
                    self._send_json({'error': 'Not found'}, 404)
            
            def log_message(self, format, *args):
                click.echo(f"[API] {args[0]}")
        
        click.echo(click.style(f"\n🚀 Data Graph Studio API Server", fg='cyan', bold=True))
        click.echo(f"   Running on http://{host}:{port}")
        click.echo(f"   Press Ctrl+C to stop\n")
        click.echo("   Endpoints:")
        click.echo("     POST /load     - Load file (body: {path: '...'})")
        click.echo("     GET  /info     - Get data info")
        click.echo("     GET  /stats    - Get statistics")
        click.echo("     POST /query    - SQL query (body: {sql: '...'})")
        click.echo("     POST /filter   - Filter data")
        click.echo("     GET  /health   - Health check\n")
        
        server = HTTPServer((host, port), APIHandler)
        server.serve_forever()
        
    except KeyboardInterrupt:
        click.echo("\n👋 Server stopped")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('file', type=click.Path(exists=True), required=False)
def gui(file: Optional[str]):
    """Launch the graphical user interface

    FILE: Optional path to data file to open immediately

    Examples:
        dgs gui                    # Open empty GUI
        dgs gui data.csv           # Open GUI with file loaded
        dgs gui sales.parquet      # Open GUI with Parquet file
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from ui.main_window import MainWindow

        # High DPI support
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("Data Graph Studio")
        app.setApplicationVersion("0.1.0")
        app.setStyle("Fusion")

        window = MainWindow()
        window.show()

        # Load file if provided
        if file:
            file_path = os.path.abspath(file)
            click.echo(f"Loading: {file_path}")
            window._load_file(file_path)

        sys.exit(app.exec())

    except ImportError as e:
        click.echo(click.style(f"Error: GUI dependencies not installed: {e}", fg='red'), err=True)
        sys.exit(1)


# ==================== Entry Point ====================

def main():
    """Main entry point"""
    cli()


if __name__ == '__main__':
    main()
