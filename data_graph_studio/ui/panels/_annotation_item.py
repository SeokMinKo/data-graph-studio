"""
AnnotationItem - Data-anchored annotation with leader line.
"""

from PySide6.QtCore import Qt
import pyqtgraph as pg


class AnnotationItem:
    """Data-anchored annotation with leader line.

    Renders a text label near a data point with a dashed leader line
    connecting the label to the exact data coordinates.  Both items
    are positioned in *data* coordinates so they follow zoom/pan.
    """

    def __init__(self, text: str, data_x: float, data_y: float,
                 offset_x: float = 0.0, offset_y: float = 0.0,
                 color: str = '#FBBF24', uid: str = ''):
        self.data_x = data_x
        self.data_y = data_y
        self.uid = uid or str(id(self))
        self.offset_x = offset_x
        self.offset_y = offset_y

        # Text item
        self.text_item = pg.TextItem(
            text=text,
            anchor=(0, 1),
            color=color,
            border=pg.mkPen('#888', width=1),
            fill=pg.mkBrush('#1E293BCC'),
        )
        self.text_item.setFont(pg.QtGui.QFont('Arial', 10))
        self.text_item.setZValue(200)

        # Leader line (data_point → label)
        self.leader = pg.PlotCurveItem(
            pen=pg.mkPen('#888', width=1, style=Qt.DashLine)
        )
        self.leader.setZValue(199)

        # Marker dot at the data point
        self.marker = pg.ScatterPlotItem(
            [data_x], [data_y], size=8,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(color),
            symbol='o',
        )
        self.marker.setZValue(201)

        self._update_position()

    def _update_position(self):
        label_x = self.data_x + self.offset_x
        label_y = self.data_y + self.offset_y
        self.text_item.setPos(label_x, label_y)
        self.leader.setData([self.data_x, label_x], [self.data_y, label_y])

    def set_offset(self, ox: float, oy: float):
        self.offset_x = ox
        self.offset_y = oy
        self._update_position()

    def add_to(self, plot_widget: pg.PlotWidget):
        plot_widget.addItem(self.text_item)
        plot_widget.addItem(self.leader)
        plot_widget.addItem(self.marker)

    def remove_from(self, plot_widget: pg.PlotWidget):
        plot_widget.removeItem(self.text_item)
        plot_widget.removeItem(self.leader)
        plot_widget.removeItem(self.marker)

    def get_text(self) -> str:
        return self.text_item.textItem.toPlainText()

    def to_dict(self) -> dict:
        return {
            'text': self.get_text(),
            'data_x': self.data_x,
            'data_y': self.data_y,
            'offset_x': self.offset_x,
            'offset_y': self.offset_y,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'AnnotationItem':
        return cls(
            text=d['text'],
            data_x=d['data_x'],
            data_y=d['data_y'],
            offset_x=d.get('offset_x', 0.0),
            offset_y=d.get('offset_y', 0.0),
        )
