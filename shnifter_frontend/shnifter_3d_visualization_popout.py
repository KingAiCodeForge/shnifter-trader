"""
Shnifter 3D Data Visualization Popout
Enterprise-ready 3D scatter/surface plot using PySide6.QtDataVisualization
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
from PySide6.QtDataVisualization import Q3DScatter, QScatter3DSeries, Q3DSurface, QSurface3DSeries, Q3DTheme
from PySide6.QtCore import Qt
import numpy as np

class Shnifter3DVisualizationPopout(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shnifter 3D Data Visualization")
        self.setMinimumSize(800, 600)
        layout = QVBoxLayout(self)

        # 3D Scatter Example
        self.scatter = Q3DScatter()
        self.scatter.setTheme(Q3DTheme.ThemeStoneMoss)
        self.scatter.setShadowQuality(Q3DScatter.ShadowQualitySoftLow)
        self.scatter.setOrthoProjection(True)
        self.scatter.setAspectRatio(1.0)
        self.scatter.setHorizontalAspectRatio(1.0)
        self.scatter.setCameraPreset(Q3DScatter.CameraPresetFront)

        # Generate random 3D data
        data = np.random.rand(100, 3) * 100
        series = QScatter3DSeries()
        series.setItemSize(0.15)
        series.setBaseColor(Qt.cyan)
        series.setItemLabelFormat("(@xLabel, @yLabel, @zLabel)")
        series.dataProxy().resetArray([
            (float(x), float(y), float(z)) for x, y, z in data
        ])
        self.scatter.addSeries(series)

        # Add to layout
        layout.addWidget(self.scatter)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
