"""
Candlestick (OHLC) Chart
"""

import numpy as np
import polars as pl
from typing import Dict, List, Any, Optional


class CandlestickChart:
    """Candlestick (OHLC) 차트"""
    
    def calculate_candles(
        self,
        df: pl.DataFrame,
        date_col: str,
        open_col: str,
        high_col: str,
        low_col: str,
        close_col: str,
        volume_col: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        캔들 데이터 계산
        
        Args:
            df: 데이터프레임
            date_col: 날짜 컬럼
            open_col: 시가 컬럼
            high_col: 고가 컬럼
            low_col: 저가 컬럼
            close_col: 종가 컬럼
            volume_col: 거래량 컬럼 (선택)
        
        Returns:
            캔들 데이터 목록
        """
        candles = []
        
        for row in df.iter_rows(named=True):
            date_val = row[date_col]
            open_val = row[open_col]
            high_val = row[high_col]
            low_val = row[low_col]
            close_val = row[close_col]
            
            candle = {
                'date': date_val,
                'open': open_val,
                'high': high_val,
                'low': low_val,
                'close': close_val,
                'bullish': close_val >= open_val,
            }
            
            if volume_col and volume_col in row:
                candle['volume'] = row[volume_col]
            
            candles.append(candle)
        
        return candles
    
    def get_plot_data(
        self,
        candles: List[Dict[str, Any]],
        width: float = 0.6
    ) -> Dict:
        """
        PyQtGraph용 플롯 데이터
        
        Args:
            candles: 캔들 데이터
            width: 캔들 너비
        
        Returns:
            플롯 데이터
        """
        n = len(candles)
        
        # 인덱스
        x = np.arange(n)
        
        # OHLC 배열
        opens = np.array([c['open'] for c in candles])
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])
        closes = np.array([c['close'] for c in candles])
        
        # 불/베어 마스크
        bullish = np.array([c['bullish'] for c in candles])
        bearish = ~bullish
        
        # 날짜 라벨
        dates = [c['date'] for c in candles]
        
        # 거래량
        volumes = None
        if 'volume' in candles[0]:
            volumes = np.array([c.get('volume', 0) for c in candles])
        
        return {
            'x': x,
            'opens': opens,
            'highs': highs,
            'lows': lows,
            'closes': closes,
            'bullish': bullish,
            'bearish': bearish,
            'dates': dates,
            'volumes': volumes,
            'width': width,
        }
    
    def calculate_indicators(
        self,
        candles: List[Dict[str, Any]],
        indicators: List[str] = None
    ) -> Dict[str, np.ndarray]:
        """
        기술적 지표 계산
        
        Args:
            candles: 캔들 데이터
            indicators: 계산할 지표 목록 ['sma_20', 'ema_10', 'bollinger', ...]
        
        Returns:
            지표별 배열
        """
        if indicators is None:
            indicators = []
        
        closes = np.array([c['close'] for c in candles])
        result = {}
        
        for ind in indicators:
            if ind.startswith('sma_'):
                period = int(ind.split('_')[1])
                result[ind] = self._sma(closes, period)
            elif ind.startswith('ema_'):
                period = int(ind.split('_')[1])
                result[ind] = self._ema(closes, period)
            elif ind == 'bollinger':
                sma = self._sma(closes, 20)
                std = self._rolling_std(closes, 20)
                result['bb_upper'] = sma + 2 * std
                result['bb_middle'] = sma
                result['bb_lower'] = sma - 2 * std
        
        return result
    
    def _sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average"""
        result = np.full_like(data, np.nan)
        for i in range(period - 1, len(data)):
            result[i] = data[i - period + 1:i + 1].mean()
        return result
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average"""
        result = np.full_like(data, np.nan)
        multiplier = 2 / (period + 1)
        
        # 첫 EMA는 SMA
        result[period - 1] = data[:period].mean()
        
        for i in range(period, len(data)):
            result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
        
        return result
    
    def _rolling_std(self, data: np.ndarray, period: int) -> np.ndarray:
        """Rolling Standard Deviation"""
        result = np.full_like(data, np.nan)
        for i in range(period - 1, len(data)):
            result[i] = data[i - period + 1:i + 1].std()
        return result
