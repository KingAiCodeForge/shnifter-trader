"""
Advanced Chart Dashboard with Multiple Chart Types and Indicators
"""
import sys
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                               QComboBox, QCheckBox, QSpinBox, QLabel, QPushButton,
                               QGroupBox, QGridLayout, QSlider, QFrame)
from PySide6.QtCore import Qt, Signal, QTimer
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from shnifter_frontend.shnifter_plotly_widget import ShnifterPlotlyWidget
    from shnifter_frontend.shnifter_plotly_widgets.chart_widget import ChartWidget
    from shnifter_frontend.shnifter_plotly_widgets.config_widget import ConfigWidget
except ImportError:
    # Fallback if imports fail
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    ShnifterPlotlyWidget = None

class AdvancedChartDashboard(QWidget):
    """Advanced chart dashboard with multiple chart types, indicators, and real-time updates"""
    
    chart_settings_changed = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Chart Dashboard")
        self.setMinimumSize(1000, 600)
        self.current_data = None
        self.indicators_enabled = {
            'sma_20': True,
            'sma_50': True,
            'ema_12': False,
            'ema_26': False,
            'bollinger_bands': False,
            'rsi': False,
            'macd': False,
            'volume': True
        }
        self.chart_type = 'candlestick'
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        # Left sidebar for controls
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)
        
        # Right area for charts
        chart_area = self.create_chart_area()
        main_layout.addWidget(chart_area, stretch=3)
        
        # Apply modern styling
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #333333;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4ff;
            }
            QComboBox, QSpinBox {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:checked {
                background-color: #00d4ff;
                border: 1px solid #00d4ff;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QSlider::groove:horizontal {
                border: 1px solid #555555;
                height: 8px;
                background: #2d2d2d;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                border: 1px solid #00d4ff;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
        """)
        
    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setFrameStyle(QFrame.StyledPanel)
        sidebar.setMaximumWidth(300)
        sidebar_layout = QVBoxLayout(sidebar)
        
        # Chart Type Selection
        chart_type_group = QGroupBox("Chart Type")
        chart_type_layout = QVBoxLayout(chart_type_group)
        
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(['Candlestick', 'OHLC', 'Line', 'Area', 'Heikin Ashi'])
        self.chart_type_combo.currentTextChanged.connect(self.on_chart_type_changed)
        chart_type_layout.addWidget(self.chart_type_combo)
        
        sidebar_layout.addWidget(chart_type_group)
        
        # Technical Indicators
        indicators_group = QGroupBox("Technical Indicators")
        indicators_layout = QGridLayout(indicators_group)
        
        row = 0
        self.indicator_checkboxes = {}
        for indicator, enabled in self.indicators_enabled.items():
            checkbox = QCheckBox(indicator.replace('_', ' ').title())
            checkbox.setChecked(enabled)
            checkbox.toggled.connect(lambda checked, ind=indicator: self.toggle_indicator(ind, checked))
            self.indicator_checkboxes[indicator] = checkbox
            indicators_layout.addWidget(checkbox, row // 2, row % 2)
            row += 1
            
        sidebar_layout.addWidget(indicators_group)
        
        # Time Frame Selection
        timeframe_group = QGroupBox("Time Frame")
        timeframe_layout = QVBoxLayout(timeframe_group)
        
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'])
        self.timeframe_combo.setCurrentText('1h')
        self.timeframe_combo.currentTextChanged.connect(self.on_timeframe_changed)
        timeframe_layout.addWidget(self.timeframe_combo)
        
        sidebar_layout.addWidget(timeframe_group)
        
        # Chart Settings
        settings_group = QGroupBox("Chart Settings")
        settings_layout = QGridLayout(settings_group)
        
        # Transparency
        settings_layout.addWidget(QLabel("Opacity:"), 0, 0)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(80)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        settings_layout.addWidget(self.opacity_slider, 0, 1)
        
        # Grid
        self.grid_checkbox = QCheckBox("Show Grid")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self.on_grid_toggled)
        settings_layout.addWidget(self.grid_checkbox, 1, 0, 1, 2)
        
        # Dark/Light theme toggle
        self.theme_checkbox = QCheckBox("Dark Theme")
        self.theme_checkbox.setChecked(True)
        self.theme_checkbox.toggled.connect(self.on_theme_toggled)
        settings_layout.addWidget(self.theme_checkbox, 2, 0, 1, 2)
        
        sidebar_layout.addWidget(settings_group)
        
        # Chart Actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        export_btn = QPushButton("📊 Export Chart")
        export_btn.clicked.connect(self.export_chart)
        actions_layout.addWidget(export_btn)
        
        reset_btn = QPushButton("🔄 Reset Zoom")
        reset_btn.clicked.connect(self.reset_zoom)
        actions_layout.addWidget(reset_btn)
        
        fullscreen_btn = QPushButton("⛶ Fullscreen")
        fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        actions_layout.addWidget(fullscreen_btn)
        
        sidebar_layout.addWidget(actions_group)
        
        sidebar_layout.addStretch()
        return sidebar
        
    def create_chart_area(self):
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        
        # Create tabs for different chart views
        self.chart_tabs = QTabWidget()
        
        # Main price chart
        if ShnifterPlotlyWidget:
            self.main_chart = ShnifterPlotlyWidget()
        else:
            # Fallback to matplotlib
            self.figure = Figure(figsize=(12, 8))
            self.main_chart = FigureCanvas(self.figure)
        
        self.chart_tabs.addTab(self.main_chart, "📈 Price Chart")
        
        # Volume chart
        if ShnifterPlotlyWidget:
            self.volume_chart = ShnifterPlotlyWidget()
        else:
            self.volume_figure = Figure(figsize=(12, 3))
            self.volume_chart = FigureCanvas(self.volume_figure)
        
        self.chart_tabs.addTab(self.volume_chart, "📊 Volume")
        
        # Indicators chart
        if ShnifterPlotlyWidget:
            self.indicators_chart = ShnifterPlotlyWidget()
        else:
            self.indicators_figure = Figure(figsize=(12, 4))
            self.indicators_chart = FigureCanvas(self.indicators_figure)
        
        self.chart_tabs.addTab(self.indicators_chart, "📉 Indicators")
        
        chart_layout.addWidget(self.chart_tabs)
        return chart_widget
        
    def update_charts(self, data, ticker=""):
        """Update all charts with new data"""
        self.current_data = data
        if data is None or data.empty:
            return
            
        try:
            self.update_main_chart(data, ticker)
            self.update_volume_chart(data, ticker)
            self.update_indicators_chart(data, ticker)
        except Exception as e:
            print(f"Error updating charts: {e}")
            
    def update_main_chart(self, data, ticker):
        """Update the main price chart"""
        if ShnifterPlotlyWidget and hasattr(self.main_chart, 'clear') and hasattr(self.main_chart, 'add_trace'):
            self.main_chart.clear()
            
            # Create candlestick or line chart based on selection
            if self.chart_type.lower() == 'candlestick':
                trace = go.Candlestick(
                    x=data.index,
                    open=data['open'],
                    high=data['high'],
                    low=data['low'],
                    close=data['close'],
                    name=ticker,
                    opacity=self.opacity_slider.value() / 100.0
                )
            else:
                trace = go.Scatter(
                    x=data.index,
                    y=data['close'],
                    mode='lines',
                    name=f"{ticker} Close",
                    line=dict(width=2)
                )
            
            self.main_chart.add_trace(trace)
            
            # Add technical indicators
            if self.indicators_enabled.get('sma_20', False) and 'sma_20' not in data.columns:
                data['sma_20'] = data['close'].rolling(window=20).mean()
            if self.indicators_enabled.get('sma_50', False) and 'sma_50' not in data.columns:
                data['sma_50'] = data['close'].rolling(window=50).mean()
                
            if self.indicators_enabled.get('sma_20', False):
                self.main_chart.add_trace(go.Scatter(
                    x=data.index, y=data['sma_20'], name='SMA 20',
                    line=dict(color='orange', width=1)
                ))
                
            if self.indicators_enabled.get('sma_50', False):
                self.main_chart.add_trace(go.Scatter(
                    x=data.index, y=data['sma_50'], name='SMA 50',
                    line=dict(color='blue', width=1)
                ))
            
            # Update layout
            self.main_chart.update_layout(
                title=f"{ticker} Price Chart",
                xaxis_title="Date",
                yaxis_title="Price",
                template="plotly_dark" if self.theme_checkbox.isChecked() else "plotly_white",
                showlegend=True,
                xaxis_rangeslider_visible=False
            )
        else:
            # Fallback to matplotlib
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.plot(data.index, data['close'], label='Close Price', linewidth=2)
            if self.indicators_enabled.get('sma_20', False):
                if 'sma_20' not in data.columns:
                    data['sma_20'] = data['close'].rolling(window=20).mean()
                ax.plot(data.index, data['sma_20'], label='SMA 20', alpha=0.7)
            ax.set_title(f"{ticker} Price Chart")
            ax.legend()
            self.figure.tight_layout()
            self.main_chart.draw()
            
    def update_volume_chart(self, data, ticker):
        """Update the volume chart"""
        if 'volume' not in data.columns:
            return
            
        if ShnifterPlotlyWidget and hasattr(self.volume_chart, 'clear'):
            self.volume_chart.clear()
            
            trace = go.Bar(
                x=data.index,
                y=data['volume'],
                name='Volume',
                marker_color='lightblue',
                opacity=0.7
            )
            
            self.volume_chart.add_trace(trace)
            self.volume_chart.update_layout(
                title=f"{ticker} Volume",
                xaxis_title="Date",
                yaxis_title="Volume",
                template="plotly_dark" if self.theme_checkbox.isChecked() else "plotly_white"
            )
        else:
            # Matplotlib fallback
            self.volume_figure.clear()
            ax = self.volume_figure.add_subplot(111)
            ax.bar(data.index, data['volume'], alpha=0.7)
            ax.set_title(f"{ticker} Volume")
            self.volume_figure.tight_layout()
            self.volume_chart.draw()
            
    def update_indicators_chart(self, data, ticker):
        """Update the indicators chart (RSI, MACD, etc.)"""
        if ShnifterPlotlyWidget and hasattr(self.indicators_chart, 'clear'):
            self.indicators_chart.clear()
            
            # Calculate RSI if enabled
            if self.indicators_enabled.get('rsi', False):
                rsi = self.calculate_rsi(data['close'])
                trace = go.Scatter(
                    x=data.index,
                    y=rsi,
                    name='RSI',
                    line=dict(color='purple')
                )
                self.indicators_chart.add_trace(trace)
                
            self.indicators_chart.update_layout(
                title=f"{ticker} Technical Indicators",
                xaxis_title="Date",
                yaxis_title="Value",
                template="plotly_dark" if self.theme_checkbox.isChecked() else "plotly_white"
            )
        
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def on_chart_type_changed(self, chart_type):
        """Handle chart type change"""
        self.chart_type = chart_type.lower()
        if self.current_data is not None:
            self.update_main_chart(self.current_data, "")
            
    def toggle_indicator(self, indicator, enabled):
        """Toggle technical indicator on/off"""
        self.indicators_enabled[indicator] = enabled
        if self.current_data is not None:
            self.update_charts(self.current_data, "")
            
    def on_timeframe_changed(self, timeframe):
        """Handle timeframe change"""
        settings = {'timeframe': timeframe}
        self.chart_settings_changed.emit(settings)
        
    def on_opacity_changed(self, value):
        """Handle opacity slider change"""
        if self.current_data is not None:
            self.update_main_chart(self.current_data, "")
            
    def on_grid_toggled(self, enabled):
        """Toggle grid display"""
        # Implementation depends on chart library
        pass
        
    def on_theme_toggled(self, dark_theme):
        """Toggle between dark and light theme"""
        if self.current_data is not None:
            self.update_charts(self.current_data, "")
            
    def export_chart(self):
        """Export chart to file"""
        # Implementation for chart export
        print("Chart export functionality")
        
    def reset_zoom(self):
        """Reset chart zoom to default"""
        # Implementation for zoom reset
        print("Reset zoom functionality")
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    dashboard = AdvancedChartDashboard()
    dashboard.show()
    
    # Test with dummy data
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    dummy_data = pd.DataFrame({
        'open': np.random.randn(len(dates)).cumsum() + 100,
        'high': np.random.randn(len(dates)).cumsum() + 105,
        'low': np.random.randn(len(dates)).cumsum() + 95,
        'close': np.random.randn(len(dates)).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, len(dates))
    }, index=dates)
    
    dashboard.update_charts(dummy_data, "TEST")
    
    app.exec()
