"""
Tests for Y-axis formula support and categorical axis detection
"""

import pytest
import numpy as np
import polars as pl


class TestCategoricalDetection:
    """Tests for categorical column detection"""

    def test_string_column_is_categorical(self):
        """String column with limited unique values should be categorical"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'category': ['A', 'B', 'C', 'A', 'B', 'C'] * 100
        })

        assert engine.is_column_categorical('category') is True

    def test_numeric_column_not_categorical(self):
        """Numeric column with many unique values should not be categorical"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'numbers': list(range(1000))
        })

        assert engine.is_column_categorical('numbers') is False

    def test_few_unique_numbers_is_categorical(self):
        """Numeric column with very few unique values should be categorical"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        # 1000 rows with only 3 unique values
        engine._df = pl.DataFrame({
            'grade': [1, 2, 3] * 334
        })

        # grade has 3 unique values out of 1002, which is 0.003 (< 0.05)
        assert engine.is_column_categorical('grade') is True

    def test_boolean_is_categorical(self):
        """Boolean column should be categorical"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'flag': [True, False, True, False, True]
        })

        assert engine.is_column_categorical('flag') is True

    def test_datetime_not_categorical(self):
        """Datetime column should not be categorical"""
        from data_graph_studio.core.data_engine import DataEngine
        from datetime import datetime

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'timestamp': [datetime(2024, 1, i) for i in range(1, 10)]
        })

        assert engine.is_column_categorical('timestamp') is False

    def test_get_unique_values(self):
        """Test getting unique values from column"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'category': ['C', 'A', 'B', 'A', 'C', 'B']
        })

        unique = engine.get_unique_values('category')
        assert unique == ['A', 'B', 'C']  # Sorted

    def test_get_unique_values_limit(self):
        """Test limiting unique values returned"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({
            'letters': [chr(65 + i) for i in range(26)]  # A-Z
        })

        unique = engine.get_unique_values('letters', limit=5)
        assert len(unique) == 5
        assert unique == ['A', 'B', 'C', 'D', 'E']

    def test_nonexistent_column(self):
        """Test handling of nonexistent column"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = pl.DataFrame({'col': [1, 2, 3]})

        assert engine.is_column_categorical('nonexistent') is False
        assert engine.get_unique_values('nonexistent') == []


class TestValueColumnFormula:
    """Tests for ValueColumn formula field"""

    def test_formula_field_exists(self):
        """ValueColumn should have formula field"""
        from data_graph_studio.core.state import ValueColumn

        vc = ValueColumn(name='test')
        assert hasattr(vc, 'formula')
        assert vc.formula == ""

    def test_formula_field_can_be_set(self):
        """ValueColumn formula can be set"""
        from data_graph_studio.core.state import ValueColumn

        vc = ValueColumn(name='test', formula='y*2')
        assert vc.formula == 'y*2'

    def test_appstate_update_value_column_formula(self):
        """AppState.update_value_column should accept formula parameter"""
        from data_graph_studio.core.state import AppState

        state = AppState()
        state.add_value_column('test_col')

        # Update formula
        state.update_value_column(0, formula='LOG(y)')

        assert state.value_columns[0].formula == 'LOG(y)'


class TestFormulaApplication:
    """Tests for applying formulas to Y data"""

    def test_simple_multiplication(self):
        """Test y*2 formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [1.0, 2.0, 3.0, 4.0, 5.0]})

        result = engine.evaluate('value * 2', df)
        expected = [2.0, 4.0, 6.0, 8.0, 10.0]

        assert result.to_list() == expected

    def test_addition(self):
        """Test y+100 formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [1.0, 2.0, 3.0]})

        result = engine.evaluate('value + 100', df)
        expected = [101.0, 102.0, 103.0]

        assert result.to_list() == expected

    def test_division(self):
        """Test y/1000 formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [1000.0, 2000.0, 3000.0]})

        result = engine.evaluate('value / 1000', df)
        expected = [1.0, 2.0, 3.0]

        assert result.to_list() == expected

    def test_log_function(self):
        """Test LOG(y) formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine
        import math

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [10.0, 100.0, 1000.0]})

        result = engine.evaluate('LOG(value)', df)
        result_list = result.to_list()

        # LOG in the engine uses natural log (ln)
        assert abs(result_list[0] - math.log(10)) < 0.001
        assert abs(result_list[1] - math.log(100)) < 0.001

    def test_sqrt_function(self):
        """Test SQRT(y) formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [4.0, 9.0, 16.0]})

        result = engine.evaluate('SQRT(value)', df)
        expected = [2.0, 3.0, 4.0]

        assert result.to_list() == expected

    def test_abs_function(self):
        """Test ABS(y) formula"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [-1.0, 2.0, -3.0]})

        result = engine.evaluate('ABS(value)', df)
        expected = [1.0, 2.0, 3.0]

        assert result.to_list() == expected

    def test_power(self):
        """Test y^2 formula (power)"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [2.0, 3.0, 4.0]})

        result = engine.evaluate('POWER(value, 2)', df)
        expected = [4.0, 9.0, 16.0]

        assert result.to_list() == expected

    def test_complex_formula(self):
        """Test complex formula: (y * 2 + 10) / 5"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({'value': [5.0, 10.0, 15.0]})

        result = engine.evaluate('(value * 2 + 10) / 5', df)
        expected = [4.0, 6.0, 8.0]

        assert result.to_list() == expected


class TestFormattedAxisCategorical:
    """Tests for categorical axis formatting"""

    def test_categorical_labels_set(self):
        """Test setting categorical labels on axis"""
        # Skip if PySide6 not available
        pytest.importorskip('PySide6')
        pytest.importorskip('pyqtgraph')

        from data_graph_studio.ui.panels.graph_panel import FormattedAxisItem

        axis = FormattedAxisItem('bottom')
        labels = ['Apple', 'Banana', 'Cherry']

        axis.set_categorical(labels)

        assert axis._is_categorical is True
        assert axis._categorical_labels == labels

    def test_categorical_clear(self):
        """Test clearing categorical mode"""
        pytest.importorskip('PySide6')
        pytest.importorskip('pyqtgraph')

        from data_graph_studio.ui.panels.graph_panel import FormattedAxisItem

        axis = FormattedAxisItem('bottom')
        axis.set_categorical(['A', 'B', 'C'])
        axis.clear_categorical()

        assert axis._is_categorical is False
        assert axis._categorical_labels is None

    def test_categorical_tick_strings(self):
        """Test tick string generation for categorical axis"""
        pytest.importorskip('PySide6')
        pytest.importorskip('pyqtgraph')

        from data_graph_studio.ui.panels.graph_panel import FormattedAxisItem

        axis = FormattedAxisItem('bottom')
        labels = ['Apple', 'Banana', 'Cherry']
        axis.set_categorical(labels)

        # Get tick strings for indices 0, 1, 2
        tick_strings = axis.tickStrings([0.0, 1.0, 2.0], 1, 1)

        assert tick_strings == ['Apple', 'Banana', 'Cherry']

    def test_categorical_tick_strings_out_of_range(self):
        """Test tick strings for out of range indices"""
        pytest.importorskip('PySide6')
        pytest.importorskip('pyqtgraph')

        from data_graph_studio.ui.panels.graph_panel import FormattedAxisItem

        axis = FormattedAxisItem('bottom')
        axis.set_categorical(['A', 'B'])

        tick_strings = axis.tickStrings([-1.0, 0.0, 1.0, 2.0, 10.0], 1, 1)

        assert tick_strings == ['', 'A', 'B', '', '']
