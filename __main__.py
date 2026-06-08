"""
Andor iDus Spectrometer Interface  — styled edition
=====================================================
UI direction: scientific dark theme
  - dark charcoal background (#0f1117)
  - cyan accent (#00e5cc)
  - monospace readouts (Courier New / system mono)
  - thin-bordered panels with subtle glow
  - pyqtgraph styled to match

iDus-specific (unchanged from previous version):
  - ReadMode = FULL_VERTICAL_BINNING
  - imageSize = xpixels (1D spectrum)
  - dtype = int16 (สัญญาณมีค่าลบได้)
  - ไม่ clip หลัง dark subtract
"""

import functools
import logging
import sys
import time
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton
)
import qtawesome as qta
import qdarktheme
import numpy as np
import pyqtgraph as pg
from pyAndorSDK2 import atmcd, atmcd_codes, atmcd_errors
from sdk_cleanup import _shutdown_sdk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Palette ────────────────────────────────────────────────────────────────
C_BG = "#0f1117"
C_PANEL = "#161b26"
C_BORDER = "#1e2736"
C_ACCENT = "#00e5cc"
C_ACCENT2 = "#0097a7"
C_TEXT = "#cdd6e8"
C_TEXT_DIM = "#4a5568"
C_WARN = "#f6ad55"
C_DANGER = "#fc8181"
C_SUCCESS = "#68d391"
C_PLOT_BG = "#0b0e14"
C_PLOT_LINE = "#00e5cc"
C_GRID = "#1a2030"

APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: "Segoe UI", "SF Pro Text", sans-serif;
    font-size: 12px;
}}
QMenuBar {{
    background-color: {C_PANEL};
    color: {C_TEXT};
    border-bottom: 1px solid {C_BORDER};
    padding: 2px 4px;
    font-size: 12px;
}}
QMenuBar::item:selected {{
    background-color: {C_BORDER};
    color: {C_ACCENT};
}}
QMenu {{
    background-color: {C_PANEL};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
}}
QMenu::item:selected {{
    background-color: {C_BORDER};
    color: {C_ACCENT};
}}

/* ── Buttons ── */
QPushButton {{
    background-color: transparent;
    color: {C_TEXT_DIM};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    padding: 6px 18px;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QPushButton:hover {{
    border-color: {C_ACCENT};
    color: {C_ACCENT};
    background-color: rgba(0,229,204,0.06);
}}
QPushButton:pressed {{
    background-color: rgba(0,229,204,0.12);
}}
QPushButton:disabled {{
    color: {C_TEXT_DIM};
    border-color: {C_BORDER};
    background-color: transparent;
}}
QPushButton#live_btn {{
    color: {C_ACCENT};
    border-color: {C_ACCENT};
}}
QPushButton#live_btn:hover {{
    background-color: rgba(0,229,204,0.1);
}}
QPushButton#live_stop_btn {{
    color: {C_DANGER};
    border-color: {C_DANGER};
}}
QPushButton#live_stop_btn:hover {{
    background-color: rgba(252,129,129,0.1);
}}

/* ── Spinboxes ── */
QSpinBox, QDoubleSpinBox {{
    background-color: {C_PANEL};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    font-family: "Courier New", monospace;
    font-size: 12px;
    min-width: 80px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {C_ACCENT};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {C_BORDER};
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {C_ACCENT2};
}}

/* ── Labels ── */
QLabel {{
    color: {C_TEXT};
    background: transparent;
}}
QLabel#dim {{
    color: {C_TEXT_DIM};
    font-size: 11px;
}}
QLabel#readout {{
    color: {C_ACCENT};
    font-family: "Courier New", monospace;
    font-size: 13px;
    font-weight: bold;
}}
QLabel#warn {{
    color: {C_WARN};
    font-size: 11px;
}}
QLabel#ok {{
    color: {C_SUCCESS};
    font-size: 11px;
}}
QLabel#err {{
    color: {C_DANGER};
    font-size: 11px;
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {C_PANEL};
    border-top: 1px solid {C_BORDER};
    color: {C_TEXT_DIM};
    font-size: 11px;
}}

/* ── Separator ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {C_BORDER};
}}

/* ── Toolbar / info bar ── */
QFrame#info_bar {{
    background-color: {C_PANEL};
    border-bottom: 1px solid {C_BORDER};
}}
QFrame#plot_frame {{
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    background-color: {C_PLOT_BG};
}}
"""



class TrafficLightButton(QPushButton):
    """ปุ่มกลม iOS + FontAwesome icon ตอน hover"""

    def __init__(self, color, hover_color, icon=None, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._hover_color = QColor(hover_color)
        self._icon = icon          # QIcon จาก qtawesome
        self._hovered = False
        self.setFixedSize(14, 14)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # วาดวงกลมพื้นฐาน
        color = self._hover_color if self._hovered else self._color
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())

        # วาด FontAwesome icon ตอน hover
        if self._hovered and self._icon:
            pixmap = self._icon.pixmap(10, 10)
            x = (self.width() - pixmap.width()) // 2
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(x, y, pixmap)

        painter.end()


# ────────────────────────────────────────────────────────────────────────────
#  IOSTitleBar  (แก้ใหม่: title_row แยกจาก menu bar)
# ────────────────────────────────────────────────────────────────────────────

class IOSTitleBar(QWidget):
    """
    Title bar 2 ชั้น:
      ชั้น 1 (title_row) : ปุ่ม 3 ปุ่ม + ชื่อ app ตรงกลาง
      ชั้น 2 (menu_row)  : รับ QMenuBar จาก inject_menubar()

    ใช้กับ QMainWindow.setMenuWidget(self.title_bar)
    เพื่อให้ menu bar อยู่ใต้ปุ่ม ไม่ลอยอยู่เหนือ
    """

    def __init__(self, window: QWidget, title: str = "Andor Viewer", parent=None):
        super().__init__(parent)
        self._window = window
        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self.setMouseTracking(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── ชั้น 1: title row ──────────────────────────────────────────────
        title_row = QWidget()
        title_row.setObjectName("title_row")
        title_row.setFixedHeight(36)
        title_row.setStyleSheet("""
            QWidget#title_row {
                background-color: #ececec;
                border-bottom: 1px solid #d0d0d0;
            }
        """)

        row_layout = QHBoxLayout(title_row)
        row_layout.setContentsMargins(12, 0, 12, 0)
        row_layout.setSpacing(8)

        # ปุ่ม 3 ปุ่ม
        icon_close = qta.icon('fa5s.times', color='#8b0000')
        icon_minimize = qta.icon('fa5s.minus', color='#8b6914')
        icon_maximize = qta.icon('fa5s.plus',  color='#1a6b24')

        self.btn_close = TrafficLightButton("#ff5f57", "#e0443e", icon_close)
        self.btn_minimize = TrafficLightButton("#febc2e", "#dea123", icon_minimize)
        self.btn_maximize = TrafficLightButton("#28c840", "#1aab29", icon_maximize)

        self.btn_close.clicked.connect(lambda: self._window.close())
        self.btn_minimize.clicked.connect(lambda: self._window.showMinimized())
        self.btn_maximize.clicked.connect(self._toggle_maximize)

        btn_box = QWidget()
        btn_box.setStyleSheet("background: transparent;")
        btn_box_layout = QHBoxLayout(btn_box)
        btn_box_layout.setContentsMargins(0, 0, 0, 0)
        btn_box_layout.setSpacing(8)
        btn_box_layout.addWidget(self.btn_close)
        btn_box_layout.addWidget(self.btn_minimize)
        btn_box_layout.addWidget(self.btn_maximize)

        # ชื่อ app กึ่งกลาง
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            "color: #555555; font-size: 13px; font-weight: 500;"
            "font-family: 'Segoe UI', sans-serif; background: transparent;"
        )

        # spacer ขวาให้สมมาตรกับ btn_box ซ้าย (62 px ≈ 3×14 + 2×8 gap + padding)
        right_placeholder = QWidget()
        right_placeholder.setFixedWidth(62)
        right_placeholder.setStyleSheet("background: transparent;")

        row_layout.addWidget(btn_box)
        row_layout.addStretch()
        row_layout.addWidget(self.title_label)
        row_layout.addStretch()
        row_layout.addWidget(right_placeholder)

        main_layout.addWidget(title_row)

        # ── ชั้น 2: รอรับ menu bar ────────────────────────────────────────
        self._menu_row = QWidget()
        self._menu_row.setObjectName("menu_row")
        self._menu_row.setStyleSheet("""
            QWidget#menu_row {
                background-color: #f5f5f5;
                border-bottom: 1px solid #d8d8d8;
            }
        """)
        self._menu_row_layout = QHBoxLayout(self._menu_row)
        self._menu_row_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_row_layout.setSpacing(0)
        main_layout.addWidget(self._menu_row)

    def inject_menubar(self, menubar: QWidget):
        """
        รับ QMenuBar จาก QMainWindow แล้วใส่ใน title bar ชั้น 2
        เรียกหลัง addMenu() ทุกอย่างเสร็จแล้ว
        """
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: transparent;
                color: {C_TEXT};
                border: none;
                padding: 2px 4px;
                font-size: 12px;
            }}
            QMenuBar::item:selected {{
                background-color: {C_BORDER};
                color: {C_ACCENT};
            }}
        """)
        self._menu_row_layout.addWidget(menubar)

    def _toggle_maximize(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # drag เพื่อย้ายหน้าต่าง (drag ได้เฉพาะบน title_row)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self._window.frameGeometry().topLeft()
            self._dragging = True
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            self._window.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

# ---------------------------------------------------------------------------
# CameraInfo
# ---------------------------------------------------------------------------


class CameraInfo:
    def __init__(self, index: int, model: str, xpixels: int, ypixels: int):
        self.index = index
        self.model = model
        self.xpixels = xpixels
        self.ypixels = ypixels

    def label(self) -> str:
        return f"{self.model}  ({self.xpixels} px)"


# ---------------------------------------------------------------------------
# SpectrometerWindow
# ---------------------------------------------------------------------------

class SpectrometerWindow(QtWidgets.QMainWindow):

    _N_DARK_FRAMES = 50

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Andor Viewer")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMinimumSize(900, 600)

        self.connected = False
        self.last_spectrum = None
        self.xpixels = 0
        self.ypixels = 0
        self.dark_current = None
        self.camera_serial = None
        self.selected_camera_index = 0
        self.camera_list: list[CameraInfo] = []
        self.live_running = False
        self._last_frame_timestamp = None
        self._accumulated_frames = 0
        self._accumulated_frame_arrays: list[np.ndarray] = []

        self.data_dir = Path(__file__).resolve().parent / "data"
        self.data_dir.mkdir(exist_ok=True)

        self.sdk = atmcd("")
        ret = self.sdk.Initialize("")
        logger.info(f"Initialize returned {ret}")
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            QtWidgets.QMessageBox.critical(
                None, "Initialization failed",
                f"Andor SDK Initialize failed ({ret}).\nThe application will close.",
            )
            sys.exit(1)

        self._init_ui()
        self.set_status("Scanning detectors…")
        self.on_cameras_ready(self._scan_camera_list())

        self._temp_timer = QtCore.QTimer(self)
        self._temp_timer.setInterval(5000)
        self._temp_timer.timeout.connect(self._do_get_temperature)

        self._live_timer = QtCore.QTimer(self)
        self._live_timer.timeout.connect(self._update_live_spectrum)

    def _init_ui(self):

        # ── 1. Title bar (ต้องทำก่อน menu bar) ───────────────────────────
        self.title_bar = IOSTitleBar(self, title="Andor Viewer")

        # ── 2. Menu bar ────────────────────────────────────────────────────
        self.camera_menu = self.menuBar().addMenu("Detector")
        self._update_camera_menu([])

        tools_menu = self.menuBar().addMenu("Tools")
        act_dark = QtWidgets.QAction(
            f"Capture Dark Current  ({self._N_DARK_FRAMES} frames)…", self)
        act_dark.triggered.connect(self._capture_dark_current)
        tools_menu.addAction(act_dark)
        act_clear = QtWidgets.QAction("Clear Dark Current", self)
        act_clear.triggered.connect(self._clear_dark_current)
        tools_menu.addAction(act_clear)

        # ── 3. Inject menu bar เข้า title bar แล้ว setMenuWidget ──────────
        #    setMenuWidget() บอก QMainWindow ว่าให้ใช้ widget นี้
        #    แทน menu bar area ทั้งหมด (title bar + menu bar รวมกัน)
        self.title_bar.inject_menubar(self.menuBar())
        self.setMenuWidget(self.title_bar)

        # ── 4. Widgets ────────────────────────────────────────────────────
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.live_button = QtWidgets.QPushButton("Live")
        self.live_button.setObjectName("live_btn")
        self.export_button = QtWidgets.QPushButton("Export")
        self.disconnect_button = QtWidgets.QPushButton("Disconnect")

        self.target_temp_spin = QtWidgets.QSpinBox()
        self.target_temp_spin.setRange(-100, 50)
        self.target_temp_spin.setValue(0)
        self.target_temp_spin.setSuffix(" °C")
        self.target_temp_spin.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.PlusMinus)

        self.exposure_spin = QtWidgets.QDoubleSpinBox()
        self.exposure_spin.setRange(0.001, 3600.0)
        self.exposure_spin.setSingleStep(0.001)
        self.exposure_spin.setDecimals(3)
        self.exposure_spin.setValue(0.001)

        self.accumulate_button = QtWidgets.QPushButton("Accumulate")
        self.accumulate_button.setObjectName("accumulate_btn")
        self.accumulate_button.setToolTip("Accumulate control button.")

        self.accumulate_count_spin = QtWidgets.QSpinBox()
        self.accumulate_count_spin.setRange(1, 1000)
        self.accumulate_count_spin.setValue(10)
        self.accumulate_count_spin.setSuffix(" frames")
        self.accumulate_count_spin.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.PlusMinus)
        self.accumulate_count_spin.setFixedWidth(110)

        self.live_accumulate_checkbox = QtWidgets.QCheckBox("Live Acc")
        self.live_accumulate_checkbox.setToolTip(
            "When checked, accumulate live frames into a NumPy array until live is stopped.")

        def _lbl(text, dim=False):
            l = QtWidgets.QLabel(text)
            if dim:
                l.setObjectName("dim")
            return l

        # ── 5. Control bar ────────────────────────────────────────────────
        ctrl_bar = QtWidgets.QFrame()
        ctrl_bar.setObjectName("info_bar")
        ctrl_layout = QtWidgets.QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(12, 8, 12, 8)
        ctrl_layout.setSpacing(8)

        ctrl_layout.addWidget(self.connect_button)
        ctrl_layout.addWidget(self.accumulate_button)
        ctrl_layout.addWidget(self.accumulate_count_spin)
        ctrl_layout.addWidget(self.live_button)
        ctrl_layout.addWidget(self.export_button)
        ctrl_layout.addWidget(self.disconnect_button)
        ctrl_layout.addSpacing(16)

        sep1 = QtWidgets.QFrame()
        sep1.setFrameShape(QtWidgets.QFrame.VLine)
        ctrl_layout.addWidget(sep1)
        ctrl_layout.addSpacing(8)

        ctrl_layout.addWidget(_lbl("TEMP TARGET", dim=True))
        ctrl_layout.addWidget(self.target_temp_spin)
        ctrl_layout.addSpacing(16)
        ctrl_layout.addWidget(_lbl("EXPOSURE", dim=True))
        ctrl_layout.addWidget(self.exposure_spin)
        ctrl_layout.addSpacing(16)
        ctrl_layout.addWidget(self.live_accumulate_checkbox)
        ctrl_layout.addSpacing(16)

        sep2 = QtWidgets.QFrame()
        sep2.setFrameShape(QtWidgets.QFrame.VLine)
        ctrl_layout.addWidget(sep2)
        ctrl_layout.addSpacing(8)
        ctrl_layout.addStretch()

        # ── 6. Info strip ─────────────────────────────────────────────────
        info_strip = QtWidgets.QFrame()
        info_strip.setObjectName("info_bar")
        info_strip_layout = QtWidgets.QHBoxLayout(info_strip)
        info_strip_layout.setContentsMargins(14, 4, 14, 4)
        info_strip_layout.setSpacing(8)

        self.current_camera_label = QtWidgets.QLabel("No detector connected")
        self.current_camera_label.setObjectName("readout")
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("dim")

        info_strip_layout.addWidget(self.current_camera_label)
        info_strip_layout.addSpacing(24)
        info_strip_layout.addWidget(self.status_label)
        info_strip_layout.addStretch()

        # ── 7. Plot ───────────────────────────────────────────────────────
        pg.setConfigOptions(
            antialias=False, foreground=C_TEXT_DIM, background=C_PLOT_BG)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(C_PLOT_BG)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel(
            "left",
            "<span style='color:#4a5568;font-size:11px'>Intensity (counts)</span>")
        self.plot_widget.setLabel(
            "bottom",
            "<span style='color:#4a5568;font-size:11px'>Pixel</span>")

        for ax in ("left", "bottom", "right", "top"):
            axis = self.plot_widget.getAxis(ax)
            axis.setPen(pg.mkPen(color=C_BORDER, width=1))
            axis.setTextPen(pg.mkPen(color=C_TEXT_DIM))
        self.plot_widget.getViewBox().setBackgroundColor(C_PLOT_BG)

        self.plot_curve = self.plot_widget.plot(
            [], pen=pg.mkPen(color=C_PLOT_LINE, width=1.2))

        plot_frame = QtWidgets.QFrame()
        plot_frame.setObjectName("plot_frame")
        pf_layout = QtWidgets.QVBoxLayout(plot_frame)
        pf_layout.setContentsMargins(1, 1, 1, 1)
        pf_layout.addWidget(self.plot_widget)

        # ── 8. Status bar ─────────────────────────────────────────────────
        self.temperature_value_label = QtWidgets.QLabel("N/A")
        self.temperature_value_label.setObjectName("readout")
        self.temperature_value_label.setFixedWidth(90)
        self.temperature_value_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.fps_value_label = QtWidgets.QLabel("N/A")
        self.fps_value_label.setObjectName("readout")
        self.fps_value_label.setFixedWidth(60)
        self.fps_value_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.accumulated_frames_value_label = QtWidgets.QLabel("0")
        self.accumulated_frames_value_label.setObjectName("readout")
        self.accumulated_frames_value_label.setFixedWidth(60)
        self.accumulated_frames_value_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.dark_label = QtWidgets.QLabel("DARK")
        self.dark_label.setObjectName("warn")
        self.dark_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        fa6s_icon = qta.icon('fa5s.circle')
        pixmap = fa6s_icon.pixmap(10, 10)
        self.dark_led_label = QtWidgets.QLabel()
        self.dark_led_label.setPixmap(pixmap)
        self.dark_led_label.setObjectName("dark_led")
        self.dark_led_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.dark_led_label.setFixedWidth(18)
        self._set_dark_led_color("#7c7c7c")

        sb_widget = QtWidgets.QWidget()
        sb_layout = QtWidgets.QHBoxLayout(sb_widget)
        sb_layout.setContentsMargins(0, 0, 8, 0)
        sb_layout.setSpacing(4)
        sb_layout.addWidget(_lbl("TEMP", dim=True))
        sb_layout.addWidget(self.temperature_value_label)
        sb_layout.addSpacing(16)
        sb_layout.addWidget(_lbl("FPS", dim=True))
        sb_layout.addWidget(self.fps_value_label)
        sb_layout.addSpacing(16)
        sb_layout.addWidget(_lbl("ACC", dim=True))
        sb_layout.addWidget(self.accumulated_frames_value_label)
        sb_layout.addSpacing(16)
        sb_layout.addWidget(self.dark_label)
        sb_layout.addWidget(self.dark_led_label)
        self.statusBar().addPermanentWidget(sb_widget)

        # ── 9. Central widget layout ──────────────────────────────────────
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(ctrl_bar)
        main_layout.addWidget(info_strip)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.addWidget(plot_frame)
        main_layout.addWidget(content, 1)

        # ── 10. Signals ───────────────────────────────────────────────────
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.accumulate_button.clicked.connect(self._do_accumulate_mode)
        self.live_button.clicked.connect(self._toggle_live)
        self.export_button.clicked.connect(self._export_spectrum)
        self.disconnect_button.clicked.connect(self._do_disconnect)
        self.exposure_spin.valueChanged.connect(self._on_exposure_changed)

        self._update_button_state()
        self.setCentralWidget(central)

    # ── Helpers ────────────────────────────────────────────────────────────
    # แทนที่ setStyleSheet("color: ...") ด้วย function นี้
    def _set_dark_led_color(self, hex_color: str):
        """เปลี่ยนสี dark LED icon"""
        icon = qta.icon('fa5s.circle', color=hex_color)
        pixmap = icon.pixmap(10, 10)
        self.dark_led_label.setPixmap(pixmap)
        
    def set_status(self, text: str):
        self.status_label.setText(text)
        logger.info(text)

    def _do_accumulate_mode(self):
        if self.live_running:
            return

        if not self.connected:
            self._do_connect(self.selected_camera_index)

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.live_button.setEnabled(False)
        self.accumulate_button.setEnabled(False)
        self.accumulate_count_spin.setEnabled(False)

        try:
            exposure_time = self.exposure_spin.value()
            accum_count = self.accumulate_count_spin.value()
            for name, call in [
                ("SetAcquisitionMode", lambda: self.sdk.SetAcquisitionMode(
                    atmcd_codes.Acquisition_Mode.ACCUMULATE)),
                ("SetReadMode", lambda: self.sdk.SetReadMode(
                    atmcd_codes.Read_Mode.FULL_VERTICAL_BINNING)),
                ("SetTriggerMode", lambda: self.sdk.SetTriggerMode(
                    atmcd_codes.Trigger_Mode.INTERNAL)),
                ("SetExposureTime", lambda: self.sdk.SetExposureTime(exposure_time)),
                ("SetNumberAccumulations",
                 lambda: self.sdk.SetNumberAccumulations(accum_count)),
                ("SetAccumulationCycleTime",
                 lambda: self.sdk.SetAccumulationCycleTime(0)),
            ]:
                ret = call()
                logger.info(f"{name} ret={ret}")
                if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                    self.set_status(f"{name} failed ({ret})")
                    return

            ret, exp, acc, kin = self.sdk.GetAcquisitionTimings()
            logger.info(f"Accumulate Count: {accum_count} exposure={exposure_time:.3f} s")
            logger.info(f"Acquisition timings: exp={exp:.3f} s, acc={acc:.3f} s, kin={kin:.3f} s")

            ret = self.sdk.StartAcquisition()
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"StartAcquisition failed ({ret})")
                return
            t0 = time.perf_counter()
            while True:
                ret, status = self.sdk.GetStatus()
                if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                    self.set_status(f"GetStatus failed ({ret})")
                    break
                logger.info(f"Status: {status}")
                if status == atmcd_errors.Error_Codes.DRV_IDLE:
                    break

                time.sleep(exp)

            t1 = time.perf_counter()
            logger.info(f"Acquisition time: {t1 - t0:.2f} s")

            ret, index = self.sdk.GetTotalNumberImagesAcquired()
            logger.info(f"TotalNumberImagesAcquired: ret={ret}, index={index}")
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"GetTotalNumberImagesAcquired failed ({ret})")
                return

            if index != 0:
                ret, arr = self.sdk.GetMostRecentImage16(self.xpixels)
                if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
                    spectrum = arr / accum_count
                    if self.dark_current is not None:
                        spectrum = spectrum - self.dark_current
                    self._display_spectrum(spectrum)
                    self.fps_value_label.setText(f"{(1/kin)*accum_count:.2f}")
                    self.accumulated_frames_value_label.setText(
                        f"{accum_count}")
            self.sdk.AbortAcquisition()
            if self.dark_current is not None:
                logger.info(f"Dark current: {self.dark_current}")
        finally:
            self._update_button_state()
            self.live_button.setEnabled(True)

    def _update_accumulated_frames_display(self):
        self.accumulated_frames_value_label.setText(
            str(self._accumulated_frames))

    def _update_button_state(self):
        self.connect_button.setEnabled(not self.connected)
        self.disconnect_button.setEnabled(
            self.connected and not self.live_running)
        self.export_button.setEnabled(self.connected and not self.live_running)
        self.accumulate_button.setEnabled(not self.live_running)
        self.accumulate_count_spin.setEnabled(not self.live_running)

    # ── Camera scan ────────────────────────────────────────────────────────

    def _scan_camera_list(self) -> list:
        logger.info("Scanning detectors")
        ret, count = self.sdk.GetAvailableCameras()
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS or count <= 0:
            return []
        ret_cur, cur_handle = self.sdk.GetCurrentCamera()
        cam_list = [info for i in range(count)
                    if (info := self._query_camera_info(self.sdk, i))]
        if ret_cur == atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.sdk.SetCurrentCamera(cur_handle)
        return cam_list

    def _query_camera_info(self, sdk, index: int):
        ret, handle = sdk.GetCameraHandle(index)
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            return None
        sdk.SetCurrentCamera(handle)
        ret, model = sdk.GetHeadModel()
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            return None
        if isinstance(model, (bytes, bytearray)):
            model = model.decode("utf-8", errors="ignore")
        model = str(model).strip()
        ret, x, y = sdk.GetDetector()
        x, y = (x, y) if ret == atmcd_errors.Error_Codes.DRV_SUCCESS else (0, 0)

        return CameraInfo(index, model, x, y)

    # ── Connect / disconnect ───────────────────────────────────────────────

    def _do_connect(self, camera_index: int):
        if self.connected:
            return

        ret, count = self.sdk.GetAvailableCameras()
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS or count <= 0:
            self.set_status(f"No detector found ({ret})")
            return

        ret, handle = self.sdk.GetCameraHandle(camera_index)
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.set_status(f"GetCameraHandle failed ({ret})")
            return
        self.sdk.SetCurrentCamera(handle)

        ret, serial = self.sdk.GetCameraSerialNumber()
        self.camera_serial = str(
            serial) if ret == atmcd_errors.Error_Codes.DRV_SUCCESS else "unknown"

        ret, temp_min, temp_max = self.sdk.GetTemperatureRange()
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            logger.info(f"Camera temp range: {temp_min} to {temp_max} °C")
        self.target_temp_spin.setRange(temp_min, temp_max)
        if not (temp_min <= self.target_temp_spin.value() <= temp_max):
            self.target_temp_spin.setValue(temp_min)

        target_temp = self.target_temp_spin.value()
        for name, call in [
            ("SetTemperature", lambda: self.sdk.SetTemperature(target_temp)),
            ("CoolerON", lambda: self.sdk.CoolerON()),
        ]:
            ret = call()
            logger.info(f"{name} ret={ret}")
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"{name} failed ({ret})")
                return

        ret, self.xpixels, self.ypixels = self.sdk.GetDetector()
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.set_status(f"GetDetector failed ({ret})")
            return

        self.plot_widget.enableAutoRange("xy", False)
        self.plot_widget.setYRange(-32768, 32767)
        self.plot_widget.setXRange(0, self.xpixels, padding=0)

        self.connected = True
        self._load_dark_current()
        self._temp_timer.start()
        self._update_button_state()

        info = next(
            (c for c in self.camera_list if c.index == camera_index), None)
        if info:
            self.current_camera_label.setText(info.label())
        self.set_status("Connected")

    def _do_disconnect(self):
        if not self.connected:
            return
        if self.live_running:
            self._stop_live()
        self.connected = False
        self.last_spectrum = None
        self.current_camera_label.setText("No detector connected")
        self.temperature_value_label.setText("N/A")
        self.fps_value_label.setText("N/A")
        self._accumulated_frames = 0
        self._update_accumulated_frames_display()
        self._last_frame_timestamp = None
        self._temp_timer.stop()
        self._update_button_state()
        self.set_status("Disconnected")

    # ── Live ───────────────────────────────────────────────────────────────

    def _toggle_live(self):
        if self.live_running:
            self._stop_live()
        else:
            if not self.connected:
                self._do_connect(self.selected_camera_index)
            if self.connected:
                self._start_live()

    def _start_live(self):
        if self.live_running or not self.connected:
            return
        exposure_time = self.exposure_spin.value()
        for name, call in [
            ("SetAcquisitionMode", lambda: self.sdk.SetAcquisitionMode(
                atmcd_codes.Acquisition_Mode.RUN_TILL_ABORT)),
            ("SetReadMode", lambda: self.sdk.SetReadMode(
                atmcd_codes.Read_Mode.FULL_VERTICAL_BINNING)),
            ("SetTriggerMode", lambda: self.sdk.SetTriggerMode(
                atmcd_codes.Trigger_Mode.INTERNAL)),
            ("SetExposureTime", lambda: self.sdk.SetExposureTime(exposure_time)),
            ("SetKineticCycleTime", lambda: self.sdk.SetKineticCycleTime(0)),
        ]:
            ret = call()
            logger.info(f"{name} ret={ret}")
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"{name} failed ({ret})")
                return

        ret = self.sdk.StartAcquisition()
        if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.set_status(f"StartAcquisition failed ({ret})")
            return
        self.live_button.setText("Stop Live")
        self.live_button.setObjectName("live_stop_btn")
        self.live_button.setStyle(self.live_button.style())
        self.live_running = True
        self._accumulated_frames = 0
        self._accumulated_frame_arrays = []
        self._update_accumulated_frames_display()
        self._update_live_interval()
        self._live_timer.start()
        self._update_button_state()
        self.set_status("Live")

    def _stop_live(self):
        if not self.live_running:
            return
        self._live_timer.stop()
        self.sdk.AbortAcquisition()
        self.live_button.setText("Live")
        self.live_button.setObjectName("live_btn")
        self.live_button.setStyle(self.live_button.style())
        self.live_running = False
        self._last_frame_timestamp = None
        self.fps_value_label.setText("N/A")
        self._update_button_state()
        self.set_status("Live stopped")

    def _export_spectrum(self):
        if self._accumulated_frame_arrays:
            spectrum = np.mean(
                np.stack(self._accumulated_frame_arrays, axis=0), axis=0).astype(np.float32)
            source = f"average of {len(self._accumulated_frame_arrays)} frames"
        elif self.last_spectrum is not None:
            spectrum = self.last_spectrum.astype(np.float32)
            source = "last frame"
        else:
            QtWidgets.QMessageBox.warning(
                self, "Nothing to export",
                "No spectrum is available to export."
            )
            return

        default_path = self.data_dir / "spectrum.csv"
        export_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Spectrum",
            str(default_path),
            "CSV Files (*.csv);;All Files (*)"
        )
        if not export_path:
            return

        try:
            pixels = np.arange(len(spectrum), dtype=np.int64)
            np.savetxt(
                export_path,
                np.column_stack((pixels, spectrum)),
                delimiter=",",
                header="pixel,intensity",
                comments=""
            )
            self.set_status(f"Exported {source} to {Path(export_path).name}")
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Exported {source} to:\n{export_path}"
            )
        except Exception as exc:
            logger.exception("Failed to export spectrum")
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Failed to export spectrum:\n{exc}"
            )

    def _update_live_spectrum(self):
        if not self.connected or not self.live_running:
            return
        ret, arr = self.sdk.GetMostRecentImage16(self.xpixels)
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            spectrum = np.array(arr, dtype=np.int16).astype(np.float32)
            if self.dark_current is not None:
                spectrum = spectrum - self.dark_current

            if self.live_accumulate_checkbox.isChecked():
                self._accumulated_frames += 1
                self._accumulated_frame_arrays.append(spectrum.copy())
            else:
                self._accumulated_frames = 1
                self._accumulated_frame_arrays = [spectrum.copy()]
            self._update_accumulated_frames_display()
            self._display_spectrum(spectrum)
            now = time.monotonic()
            if self._last_frame_timestamp is not None:
                dt = now - self._last_frame_timestamp
                if dt > 0:
                    self.fps_value_label.setText(f"{1.0/dt:.2f}")
            self._last_frame_timestamp = now
            return
        if ret == atmcd_errors.Error_Codes.DRV_NO_NEW_DATA:
            return
        self.set_status(f"Acquisition error ({ret})")
        self._stop_live()

    def _update_live_interval(self):

        interval = 100  # default to 100 ms if we can't get timings
        ret, exp, acc, kin = self.sdk.GetAcquisitionTimings()
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            # poll slightly faster than acquisition
            interval = int(kin * 1000 * 0.8)
        self._live_timer.setInterval(max(5, interval))

    def _display_spectrum(self, spectrum: np.ndarray):
        self.last_spectrum = spectrum
        self.plot_curve.setData(spectrum)

    # ── Dark current ───────────────────────────────────────────────────────

    def _dark_current_path(self, exposure: float) -> Path:
        return self.data_dir / f"{self.camera_serial or 'unknown'}_{exposure:.3f}_{self._N_DARK_FRAMES}.npy"

    def _load_dark_current(self):
        fp = self._dark_current_path(self.exposure_spin.value())
        if not fp.exists():
            self.dark_current = None
            self.dark_label.setText("DARK")
            self.dark_label.setObjectName("warn")
            self.dark_label.setStyle(self.dark_label.style())
            self._set_dark_led_color("#8b0000")
            return
        try:
            frames = np.load(fp)
            self.dark_current = frames.astype(np.float32)
            self.dark_label.setText("DARK")
            self.dark_label.setObjectName("ok")
            self.dark_label.setStyle(self.dark_label.style())
            self._set_dark_led_color("#1a6b24")
            logger.info(f"Loaded dark: {fp}")
        except Exception as exc:
            self.dark_current = None
            self.dark_label.setText("DARK")
            self.dark_label.setObjectName("err")
            self.dark_label.setStyle(self.dark_label.style())
            self._set_dark_led_color("#8b0000")
            logger.warning(f"Dark load failed: {exc}")

    def _clear_dark_current(self):
        self.dark_current = None
        self.dark_label.setText("DARK")
        self.dark_label.setObjectName("warn")
        self.dark_label.setStyle(self.dark_label.style())
        self._set_dark_led_color("#8b0000")
        self.set_status("Dark current cleared")
        fp = self._dark_current_path(self.exposure_spin.value())
        if fp.exists():
            try:
                fp.unlink()
                logger.info(f"Deleted dark current file: {fp}")
            except Exception as exc:
                logger.warning(f"Failed to delete dark current file: {exc}")

    def _capture_dark_current(self):
        if not self.connected:
            QtWidgets.QMessageBox.warning(self, "Not connected",
                                          "Please connect a detector before capturing dark current.")
            return

        exposure = self.exposure_spin.value()
        save_path = self._dark_current_path(exposure)
        n = self._N_DARK_FRAMES
        was_live = self.live_running
        if was_live:
            self._stop_live()

        try:
            for name, call in [
                ("SetAcquisitionMode", lambda: self.sdk.SetAcquisitionMode(
                    atmcd_codes.Acquisition_Mode.ACCUMULATE)),
                ("SetReadMode", lambda: self.sdk.SetReadMode(
                    atmcd_codes.Read_Mode.FULL_VERTICAL_BINNING)),
                ("SetTriggerMode", lambda: self.sdk.SetTriggerMode(
                    atmcd_codes.Trigger_Mode.INTERNAL)),
                ("SetExposureTime", lambda: self.sdk.SetExposureTime(exposure)),
                ("SetNumberAccumulations",
                 lambda: self.sdk.SetNumberAccumulations(n)),
                ("SetAccumulationCycleTime",
                 lambda: self.sdk.SetAccumulationCycleTime(0)),
            ]:
                ret = call()
                logger.info(f"{name} ret={ret}")
                if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                    self.set_status(f"{name} failed ({ret})")
                    return

            ret, exp, acc, kin = self.sdk.GetAcquisitionTimings()
            logger.info(f"Accumulate Count: {n} exposure={exposure:.3f} s")
            logger.info(f"Acquisition timings: exp={exp:.3f} s, acc={acc:.3f} s, kin={kin:.3f} s")

            ret = self.sdk.StartAcquisition()
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"StartAcquisition failed ({ret})")
                return
            t0 = time.perf_counter()
            while True:
                ret, status = self.sdk.GetStatus()
                if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                    self.set_status(f"GetStatus failed ({ret})")
                    break
                if status == atmcd_errors.Error_Codes.DRV_IDLE:
                    break

                time.sleep(exp)

            t1 = time.perf_counter()
            logger.info(f"Acquisition time: {t1 - t0:.2f} s")

            ret, index = self.sdk.GetTotalNumberImagesAcquired()
            logger.info(f"TotalNumberImagesAcquired: ret={ret}, index={index}")
            if ret != atmcd_errors.Error_Codes.DRV_SUCCESS:
                self.set_status(f"GetTotalNumberImagesAcquired failed ({ret})")
                return

            if index != 0:
                ret, arr = self.sdk.GetMostRecentImage16(self.xpixels)
                if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
                    frame = arr / n
                    np.save(save_path, frame)
            self.sdk.AbortAcquisition()
            if self.dark_current is not None:
                logger.info(f"Dark current: {self.dark_current}")
        except Exception as exc:
            logger.exception("Dark capture failed")
            QtWidgets.QMessageBox.critical(self, "Capture failed",
                                          f"An error occurred during dark capture:\n{exc}")
            return
        
        self._load_dark_current()
        self.set_status(f"Dark saved: {save_path.name}")
        QtWidgets.QMessageBox.information(self, "Dark current saved",
                                          f"Saved {n} frames to:\n{save_path}")
        if was_live:
            self._start_live()

    # ── Temperature ────────────────────────────────────────────────────────

    def _do_get_temperature(self):
        if not self.connected:
            return
        ret, temp, *_ = self.sdk.GetTemperatureStatus()
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            self.temperature_value_label.setText(f"{temp:.1f} °C")
        else:
            self.temperature_value_label.setText("N/A")

    # ── Exposure ───────────────────────────────────────────────────────────

    def _on_exposure_changed(self, value: float):
        if not self.connected:
            return
        was_live = self.live_running
        if was_live:
            self._stop_live()
        ret = self.sdk.SetExposureTime(value)
        if ret == atmcd_errors.Error_Codes.DRV_SUCCESS:
            self._load_dark_current()
            self.set_status(f"Exposure  {value:.3f} s")
        else:
            self.set_status(f"SetExposureTime failed ({ret})")
        if was_live:
            self._start_live()

    # ── Connect button ─────────────────────────────────────────────────────

    def _on_connect_clicked(self):
        self.connect_button.setEnabled(False)
        self.set_status("Connecting…")
        self._do_connect(self.selected_camera_index)

    # ── Detector menu ──────────────────────────────────────────────────────

    def _update_camera_menu(self, cam_list: list):
        self.camera_menu.clear()
        if not cam_list:
            a = QtWidgets.QAction("No detectors available", self)
            a.setEnabled(False)
            self.camera_menu.addAction(a)
            return
        group = QtWidgets.QActionGroup(self)
        group.setExclusive(True)
        for info in cam_list:
            a = QtWidgets.QAction(info.label(), self)
            a.setCheckable(True)
            a.setChecked(info.index == self.selected_camera_index)
            a.setActionGroup(group)
            a.triggered.connect(functools.partial(
                self._select_camera, info.index))
            self.camera_menu.addAction(a)

    def _select_camera(self, index: int):
        self.selected_camera_index = index
        if self.connected:
            self._do_disconnect()
            self._do_connect(index)
        self._update_button_state()

    @QtCore.pyqtSlot(list)
    def on_cameras_ready(self, cam_list: list):
        self.camera_list = cam_list
        self._update_camera_menu(cam_list)
        if cam_list:
            self.set_status(f"Found {len(cam_list)} detector(s)")
        else:
            self.set_status("No detectors found")
            QtCore.QTimer.singleShot(0, self._notify_no_camera_and_exit)

    def _notify_no_camera_and_exit(self):
        QtWidgets.QMessageBox.critical(self, "No detectors",
                                       "No detectors connected. The application will close.")
        self.close()

    # ── Cleanup ────────────────────────────────────────────────────────────

    def closeEvent(self, event: QtGui.QCloseEvent):
        was_live = self.live_running
        was_connected = self.connected
        try:
            self._temp_timer.stop()
            self._live_timer.stop()
            if was_connected:
                self._do_disconnect()
            _shutdown_sdk(self.sdk, live_running=was_live, connected=was_connected)
        except Exception as exc:
            logger.warning("Cleanup during closeEvent failed: %s", exc)
        finally:
            self.live_running = False
            self.connected = False
            self._update_button_state()
            self.sdk = None
            logger.info("Application exited")
            event.accept()


# ---------------------------------------------------------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(qdarktheme.load_stylesheet("light"))
    window = SpectrometerWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
