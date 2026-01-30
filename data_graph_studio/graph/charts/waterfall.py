"""
Waterfall Chart
"""

import numpy as np
import polars as pl
from typing import Dict, List, Any, Optional


class WaterfallChart:
    """Waterfall 차트"""
    
    # 타입별 기본 색상
    TYPE_COLORS = {
        'start': 'gray',
        'increase': 'green',
        'decrease': 'red',
        'total': 'blue',
        'subtotal': 'darkblue',
    }
    
    def calculate_waterfall(
        self,
        df: pl.DataFrame,
        category_col: str,
        value_col: str,
        type_col: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Waterfall 데이터 계산
        
        Args:
            df: 데이터프레임
            category_col: 카테고리 컬럼
            value_col: 값 컬럼
            type_col: 타입 컬럼 ('start', 'increase', 'decrease', 'total')
                      None이면 값의 부호로 자동 결정
        
        Returns:
            Waterfall 데이터 목록
        """
        result = []
        running_total = 0
        
        for i, row in enumerate(df.iter_rows(named=True)):
            category = row[category_col]
            value = row[value_col]
            
            # 타입 결정
            if type_col and type_col in row:
                item_type = row[type_col]
            else:
                # 자동 결정
                if i == 0:
                    item_type = 'start'
                elif value > 0:
                    item_type = 'increase'
                elif value < 0:
                    item_type = 'decrease'
                else:
                    item_type = 'total'
            
            # 시작/끝 위치 계산
            if item_type in ('start', 'total', 'subtotal'):
                # Start/Total: 0에서 시작
                if item_type == 'start':
                    start = 0
                    end = value
                    running_total = value
                else:
                    # Total: 현재 누적값 표시
                    start = 0
                    end = running_total
            else:
                # Increase/Decrease: 이전 위치에서 시작
                start = running_total
                end = running_total + value
                running_total = end
            
            result.append({
                'category': category,
                'value': value,
                'start': start,
                'end': end,
                'type': item_type,
                'color': self.TYPE_COLORS.get(item_type, 'gray'),
            })
        
        return result
    
    def get_plot_data(
        self,
        waterfall_data: List[Dict[str, Any]],
        width: float = 0.6
    ) -> Dict:
        """
        PyQtGraph용 플롯 데이터
        
        Args:
            waterfall_data: Waterfall 데이터
            width: 막대 너비
        
        Returns:
            플롯 데이터
        """
        n = len(waterfall_data)
        
        categories = [d['category'] for d in waterfall_data]
        starts = np.array([d['start'] for d in waterfall_data])
        ends = np.array([d['end'] for d in waterfall_data])
        colors = [d['color'] for d in waterfall_data]
        types = [d['type'] for d in waterfall_data]
        
        # 막대 높이 (음수 가능)
        heights = ends - starts
        
        # 연결선 데이터
        connectors = []
        for i in range(n - 1):
            if types[i] not in ('total', 'subtotal'):
                connectors.append({
                    'x1': i + width / 2,
                    'x2': i + 1 - width / 2,
                    'y': ends[i],
                })
        
        return {
            'x': np.arange(n),
            'categories': categories,
            'starts': starts,
            'heights': heights,
            'colors': colors,
            'types': types,
            'connectors': connectors,
            'width': width,
        }
    
    def set_custom_colors(self, colors: Dict[str, str]):
        """커스텀 색상 설정"""
        self.TYPE_COLORS.update(colors)
