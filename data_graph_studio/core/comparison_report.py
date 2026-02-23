"""
Comparison Report Generator - 비교 리포트 생성기

데이터셋 비교 결과를 다양한 형식(HTML, CSV, JSON)으로 내보내기
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any

from .data_engine import DataEngine
from .state import AppState

logger = logging.getLogger(__name__)


class ComparisonReport:
    """비교 리포트 생성"""

    def __init__(self, engine: DataEngine, state: AppState):
        self.engine = engine
        self.state = state

    def generate_report_data(self, dataset_ids: List[str] = None) -> Dict[str, Any]:
        """
        리포트 데이터 생성

        Args:
            dataset_ids: 비교할 데이터셋 ID 목록 (None이면 state에서 가져옴)

        Returns:
            리포트 데이터 딕셔너리
        """
        if dataset_ids is None:
            dataset_ids = self.state.comparison_dataset_ids

        if not dataset_ids:
            return {"error": "No datasets to compare"}

        report = {
            "title": "Data Comparison Report",
            "generated_at": datetime.now().isoformat(),
            "comparison_mode": self.state.comparison_mode.value,
            "datasets": [],
            "common_columns": [],
            "statistics": {},
            "statistical_tests": [],
            "correlations": []
        }

        # Dataset information
        for did in dataset_ids:
            metadata = self.state.get_dataset_metadata(did)
            dataset = self.engine.get_dataset(did)

            if metadata:
                ds_info = {
                    "id": did,
                    "name": metadata.name,
                    "file_path": metadata.file_path,
                    "row_count": metadata.row_count,
                    "column_count": metadata.column_count,
                    "color": metadata.color
                }
            elif dataset:
                ds_info = {
                    "id": did,
                    "name": dataset.name,
                    "row_count": dataset.row_count,
                    "column_count": dataset.column_count,
                    "color": dataset.color
                }
            else:
                ds_info = {"id": did, "name": did}

            report["datasets"].append(ds_info)

        # Common columns
        common_cols = self.engine.get_common_columns(dataset_ids)
        report["common_columns"] = common_cols

        # Get numeric columns
        numeric_cols = []
        for col in common_cols:
            ds = self.engine.get_dataset(dataset_ids[0])
            if ds and ds.df is not None and col in ds.df.columns:
                dtype = str(ds.df[col].dtype)
                if dtype.startswith(('Int', 'Float', 'UInt')):
                    numeric_cols.append(col)

        # Statistics for each numeric column
        for col in numeric_cols[:5]:  # Limit to 5 columns
            stats = self.engine.calculate_descriptive_comparison(dataset_ids, col)
            report["statistics"][col] = stats

        # Statistical tests between pairs
        if len(dataset_ids) >= 2 and numeric_cols:
            for col in numeric_cols[:3]:  # Limit columns
                for i in range(len(dataset_ids)):
                    for j in range(i + 1, len(dataset_ids)):
                        test_result = self.engine.perform_statistical_test(
                            dataset_ids[i], dataset_ids[j], col, "auto"
                        )
                        if test_result and "error" not in test_result:
                            test_result["dataset_a"] = dataset_ids[i]
                            test_result["dataset_b"] = dataset_ids[j]
                            test_result["column"] = col
                            report["statistical_tests"].append(test_result)

        # Correlations between pairs
        if len(dataset_ids) >= 2 and numeric_cols:
            for col in numeric_cols[:3]:
                for i in range(len(dataset_ids)):
                    for j in range(i + 1, len(dataset_ids)):
                        corr_result = self.engine.calculate_correlation(
                            dataset_ids[i], dataset_ids[j], col, col, "pearson"
                        )
                        if corr_result and "error" not in corr_result:
                            corr_result["dataset_a"] = dataset_ids[i]
                            corr_result["dataset_b"] = dataset_ids[j]
                            corr_result["column"] = col
                            report["correlations"].append(corr_result)

        return report

    def export_html(self, file_path: str, dataset_ids: List[str] = None) -> bool:
        """
        HTML 형식으로 내보내기

        Args:
            file_path: 저장 경로
            dataset_ids: 비교할 데이터셋 ID 목록

        Returns:
            성공 여부
        """
        data = self.generate_report_data(dataset_ids)

        if "error" in data:
            return False

        html = self._generate_html_report(data)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html)
            return True
        except Exception:
            logger.error("comparison_report.export_html.failed", extra={"path": file_path}, exc_info=True)
            return False

    def _generate_html_report(self, data: Dict[str, Any]) -> str:
        """HTML 리포트 생성"""
        parts = [
            self._render_html_head(data),
            self._render_html_datasets_section(data),
            self._render_html_stats_section(data),
            self._render_html_tests_section(data),
            self._render_html_correlations_section(data),
            self._render_html_footer(),
        ]
        return "".join(parts)

    def _render_html_head(self, data: Dict[str, Any]) -> str:
        """Render DOCTYPE, head with inline CSS, and opening body/container tags."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{data['title']}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .report-container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{ color: #1976d2; border-bottom: 2px solid #1976d2; padding-bottom: 10px; }}
        h2 {{ color: #424242; margin-top: 30px; }}
        .meta-info {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f5f5f5; }}
        .dataset-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            color: white;
            font-weight: 500;
            margin-right: 8px;
        }}
        .stat-card {{ background: #f8f9fa; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .significance {{ font-weight: bold; }}
        .sig-high {{ color: #d32f2f; }}
        .sig-medium {{ color: #f57c00; }}
        .sig-low {{ color: #388e3c; }}
        .sig-none {{ color: #757575; }}
        .positive {{ color: #388e3c; }}
        .negative {{ color: #d32f2f; }}
    </style>
</head>
<body>
    <div class="report-container">
        <h1>{data['title']}</h1>
        <p class="meta-info">
            Generated: {data['generated_at']}<br>
            Comparison Mode: {data['comparison_mode'].replace('_', ' ').title()}
        </p>
"""

    def _render_html_datasets_section(self, data: Dict[str, Any]) -> str:
        """Render the Datasets summary table."""
        rows = ""
        for ds in data['datasets']:
            color = ds.get('color', '#1f77b4')
            rows += f"""
                <tr>
                    <td><span class="dataset-badge" style="background-color: {color}">{ds.get('name', ds['id'])}</span></td>
                    <td>{ds.get('row_count', 'N/A'):,}</td>
                    <td>{ds.get('column_count', 'N/A')}</td>
                </tr>
"""
        return f"""
        <h2>Datasets</h2>
        <table>
            <thead><tr><th>Name</th><th>Rows</th><th>Columns</th></tr></thead>
            <tbody>{rows}            </tbody>
        </table>
"""

    def _render_html_stats_section(self, data: Dict[str, Any]) -> str:
        """Render the Descriptive Statistics section."""
        if not data.get('statistics'):
            return ""
        ds_name_map = {ds['id']: ds.get('name', ds['id']) for ds in data['datasets']}
        parts = ["\n        <h2>Descriptive Statistics</h2>\n"]
        for col, stats in data['statistics'].items():
            rows = ""
            for did, ds_stats in stats.items():
                mean = ds_stats.get('mean', 'N/A')
                std = ds_stats.get('std', 'N/A')
                min_val = ds_stats.get('min', 'N/A')
                max_val = ds_stats.get('max', 'N/A')
                count = ds_stats.get('count', 'N/A')
                rows += f"""
                    <tr>
                        <td>{ds_name_map.get(did, did)}</td>
                        <td>{mean:,.2f if isinstance(mean, (int, float)) else mean}</td>
                        <td>{std:,.2f if isinstance(std, (int, float)) else std}</td>
                        <td>{min_val:,.2f if isinstance(min_val, (int, float)) else min_val}</td>
                        <td>{max_val:,.2f if isinstance(max_val, (int, float)) else max_val}</td>
                        <td>{count:,} if isinstance(count, int) else count</td>
                    </tr>
"""
            parts.append(f"""
        <div class="stat-card">
            <h3 style="margin-top: 0;">{col}</h3>
            <table>
                <thead>
                    <tr><th>Dataset</th><th>Mean</th><th>Std</th><th>Min</th><th>Max</th><th>Count</th></tr>
                </thead>
                <tbody>{rows}                </tbody>
            </table>
        </div>
""")
        return "".join(parts)

    def _render_html_tests_section(self, data: Dict[str, Any]) -> str:
        """Render the Statistical Tests section (empty string if no tests)."""
        if not data.get('statistical_tests'):
            return ""
        ds_name_map = {ds['id']: ds.get('name', ds['id']) for ds in data['datasets']}
        rows = ""
        for test in data['statistical_tests']:
            p_val = test.get('p_value', 0)
            if p_val < 0.001:
                sig_class, sig_text = 'sig-high', '*** p < 0.001'
            elif p_val < 0.01:
                sig_class, sig_text = 'sig-medium', '** p < 0.01'
            elif p_val < 0.05:
                sig_class, sig_text = 'sig-low', '* p < 0.05'
            else:
                sig_class, sig_text = 'sig-none', 'NS'
            ds_a = ds_name_map.get(test['dataset_a'], test['dataset_a'])
            ds_b = ds_name_map.get(test['dataset_b'], test['dataset_b'])
            rows += f"""
                <tr>
                    <td>{test.get('column', 'N/A')}</td>
                    <td>{ds_a} vs {ds_b}</td>
                    <td>{test.get('test_name', 'N/A')}</td>
                    <td>{test.get('statistic', 'N/A'):.4f if test.get('statistic') else 'N/A'}</td>
                    <td>{test.get('p_value', 'N/A'):.6f if test.get('p_value') else 'N/A'}</td>
                    <td class="significance {sig_class}">{sig_text}</td>
                    <td>{test.get('effect_size', 'N/A'):.3f if test.get('effect_size') else 'N/A'}</td>
                </tr>
"""
        return f"""
        <h2>Statistical Tests</h2>
        <table>
            <thead>
                <tr>
                    <th>Column</th><th>Comparison</th><th>Test</th>
                    <th>Statistic</th><th>p-value</th><th>Significance</th><th>Effect Size</th>
                </tr>
            </thead>
            <tbody>{rows}            </tbody>
        </table>
"""

    def _render_html_correlations_section(self, data: Dict[str, Any]) -> str:
        """Render the Correlations section (empty string if no correlations)."""
        if not data.get('correlations'):
            return ""
        ds_name_map = {ds['id']: ds.get('name', ds['id']) for ds in data['datasets']}
        rows = ""
        for corr in data['correlations']:
            r = corr.get('correlation', 0)
            color_class = 'positive' if r > 0 else 'negative'
            ds_a = ds_name_map.get(corr['dataset_a'], corr['dataset_a'])
            ds_b = ds_name_map.get(corr['dataset_b'], corr['dataset_b'])
            rows += f"""
                <tr>
                    <td>{corr.get('column', 'N/A')}</td>
                    <td>{ds_a} vs {ds_b}</td>
                    <td class="{color_class}">{r:.4f if r else 'N/A'}</td>
                    <td>{corr.get('p_value', 'N/A'):.6f if corr.get('p_value') else 'N/A'}</td>
                    <td>{corr.get('strength', 'N/A').title() if corr.get('strength') else 'N/A'}</td>
                </tr>
"""
        return f"""
        <h2>Correlations</h2>
        <table>
            <thead>
                <tr>
                    <th>Column</th><th>Comparison</th><th>Correlation (r)</th>
                    <th>p-value</th><th>Strength</th>
                </tr>
            </thead>
            <tbody>{rows}            </tbody>
        </table>
"""

    @staticmethod
    def _render_html_footer() -> str:
        """Render the closing footer, container div, and HTML tags."""
        return """
        <hr style="margin-top: 40px; border: none; border-top: 1px solid #ddd;">
        <p style="color: #999; font-size: 12px; text-align: center;">
            Generated by Data Graph Studio
        </p>
    </div>
</body>
</html>
"""

    def export_json(self, file_path: str, dataset_ids: List[str] = None) -> bool:
        """JSON 형식으로 내보내기"""
        data = self.generate_report_data(dataset_ids)

        if "error" in data:
            return False

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception:
            logger.error("comparison_report.export_json.failed", extra={"path": file_path}, exc_info=True)
            return False

    def export_csv(self, file_path: str, dataset_ids: List[str] = None) -> bool:
        """CSV 형식으로 내보내기 (통계 테이블)"""
        data = self.generate_report_data(dataset_ids)

        if "error" in data:
            return False

        try:
            import csv

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow(['Data Comparison Report'])
                writer.writerow(['Generated', data['generated_at']])
                writer.writerow([])

                # Datasets
                writer.writerow(['Datasets'])
                writer.writerow(['Name', 'Rows', 'Columns'])
                for ds in data['datasets']:
                    writer.writerow([
                        ds.get('name', ds['id']),
                        ds.get('row_count', 'N/A'),
                        ds.get('column_count', 'N/A')
                    ])
                writer.writerow([])

                # Statistics
                writer.writerow(['Statistics'])
                for col, stats in data.get('statistics', {}).items():
                    writer.writerow([f'Column: {col}'])
                    writer.writerow(['Dataset', 'Mean', 'Std', 'Min', 'Max', 'Count'])
                    for did, ds_stats in stats.items():
                        ds_name = did
                        for ds in data['datasets']:
                            if ds['id'] == did:
                                ds_name = ds.get('name', did)
                                break
                        writer.writerow([
                            ds_name,
                            ds_stats.get('mean', ''),
                            ds_stats.get('std', ''),
                            ds_stats.get('min', ''),
                            ds_stats.get('max', ''),
                            ds_stats.get('count', '')
                        ])
                    writer.writerow([])

                # Statistical tests
                if data.get('statistical_tests'):
                    writer.writerow(['Statistical Tests'])
                    writer.writerow(['Column', 'Dataset A', 'Dataset B', 'Test', 'Statistic', 'p-value', 'Significant', 'Effect Size'])
                    for test in data['statistical_tests']:
                        writer.writerow([
                            test.get('column', ''),
                            test.get('dataset_a', ''),
                            test.get('dataset_b', ''),
                            test.get('test_name', ''),
                            test.get('statistic', ''),
                            test.get('p_value', ''),
                            test.get('is_significant', ''),
                            test.get('effect_size', '')
                        ])

            return True
        except Exception:
            logger.error("comparison_report.export_csv.failed", extra={"path": file_path}, exc_info=True)
            return False
