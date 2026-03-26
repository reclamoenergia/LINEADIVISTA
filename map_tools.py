# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand


class ManualLineMapTool(QgsMapTool):
    """Map tool for collecting a polyline in click order."""

    lineCompleted = pyqtSignal(object)  # QgsGeometry
    canceled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        self.rubber = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.rubber.setColor(QColor(0, 120, 215, 180))
        self.rubber.setWidth(2)

    def activate(self):
        super().activate()
        self._reset()

    def deactivate(self):
        self._reset()
        super().deactivate()

    def _reset(self):
        self.points = []
        self.rubber.reset(QgsWkbTypes.LineGeometry)

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = self.toMapCoordinates(event.pos())
            self.points.append(QgsPointXY(point))
            self.rubber.addPoint(point, True)
        elif event.button() == Qt.RightButton:
            if len(self.points) >= 2:
                geom = QgsGeometry.fromPolylineXY(self.points)
                self.lineCompleted.emit(geom)
            else:
                self.canceled.emit()
            self._reset()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._reset()
            self.canceled.emit()
