"""
Violin Plot Chart
"""

import numpy as np
import polars as pl
from typing import Dict, List, Any
from scipy import stats as scipy_stats


class ViolinPlotChart:
    """Violin Plot 차트"""
    
    def calculate_density(
        self,
        df: pl.DataFrame,
        category_col: str,
        value_col: str,
        n_points: int = 100,
        include_box: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        KDE 밀도 계산
        
        Args:
            df: 데이터프레임
            category_col: 카테고리 컬럼
            value_col: 값 컬럼
            n_points: 밀도 포인트 수
            include_box: Box plot 통계 포함 여부
        
        Returns:
            카테고리별 밀도 데이터
        """
        result = {}
        
        categories = df[category_col].unique().to_list()
        
        for cat in categories:
            cat_data = df.filter(pl.col(category_col) == cat)[value_col].to_numpy()
            cat_data = cat_data[~np.isnan(cat_data)]
            
            if len(cat_data) < 2:
                continue
            
            # KDE 계산
            try:
                kde = scipy_stats.gaussian_kde(cat_data)
            except np.linalg.LinAlgError:
                # Singular matrix - skip
                continue
            
            # 밀도 범위 결정
            data_min = cat_data.min()
            data_max = cat_data.max()
            margin = (data_max - data_min) * 0.1
            
            x = np.linspace(data_min - margin, data_max + margin, n_points)
            y = kde(x)
            
            # 정규화 (최대값 = 1)
            if y.max() > 0:
                y = y / y.max()
            
            entry = {
                'x': x.tolist(),
                'y': y.tolist(),
            }
            
            # Box plot 통계 추가
            if include_box:
                entry['median'] = float(np.median(cat_data))
                entry['q1'] = float(np.percentile(cat_data, 25))
                entry['q3'] = float(np.percentile(cat_data, 75))
                entry['min'] = float(cat_data.min())
                entry['max'] = float(cat_data.max())
            
            result[cat] = entry
        
        return result
    
    def get_plot_data(
        self,
        density: Dict[str, Dict[str, Any]],
        width: float = 0.8
    ) -> List[Dict]:
        """
        PyQtGraph용 플롯 데이터 생성
        
        Args:
            density: 밀도 데이터
            width: Violin 너비
        
        Returns:
            Violin 플롯 데이터 목록
        """
        violins = []
        
        for i, (cat, data) in enumerate(density.items()):
            x = np.array(data['x'])
            y = np.array(data['y']) * width / 2
            
            # 좌우 대칭 폴리곤
            left_x = i - y
            right_x = i + y
            
            # 폴리곤 경로
            path_x = np.concatenate([left_x, right_x[::-1]])
            path_y = np.concatenate([x, x[::-1]])
            
            violins.append({
                'category': cat,
                'index': i,
                'path_x': path_x.tolist(),
                'path_y': path_y.tolist(),
                'median': data.get('median'),
                'q1': data.get('q1'),
                'q3': data.get('q3'),
            })
        
        return violins
