import sys
import threading
import json
import os
import re
import time
import logging
import psutil
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QTextEdit, QLabel, QFrame, QStackedWidget,
    QLineEdit, QListWidget, QListWidgetItem, QGraphicsDropShadowEffect,
    QInputDialog, QFileDialog, QSlider, QCheckBox, QGroupBox,
    QProgressBar, QTabWidget, QSplitter, QScrollArea, QToolButton,
    QSizePolicy, QSpinBox, QDoubleSpinBox, QMessageBox, QMenu
)
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt, QThread, pyqtSlot, QRect
from PyQt6.QtGui import QFont, QColor, QTextCursor, QPalette, QAction, QImage, QPixmap, QPainter, QBrush, QPen
import cv2

try:
    from memory_core import AgentMemory
    from ai_core import LocalAgentBrain
    from vision_loop import DesktopVisionSystem, CaptureConfig
    from voice_core import VoiceSystem, VoiceConfig
    from action_core import InputAutomationSystem, ActionConfig
except ImportError as e:
    print(f"Subsystem import warning: {e}. Implementing Mock fallbacks for layout testing.")
    class AgentMemory: 
        def __init__(self): self.rules = []; self.failure_log = []
    class LocalAgentBrain: pass
    class DesktopVisionSystem: pass
    class VoiceSystem:
        def __init__(self, cfg): raise RuntimeError("COM entry point execution failure")
    class InputAutomationSystem: pass
    class CaptureConfig: pass
    class VoiceConfig: pass
    class ActionConfig: pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("nexus.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MainSoftware")

PALETTE = {
    "bg_deep":     "#080A0F",
    "bg_panel":    "#0D1117",
    "bg_card":     "#161B22",
    "bg_input":    "#1C2333",
    "accent":      "#00FFCC",
    "accent2":     "#3FB950",
    "accent_red":  "#FF3366",
    "accent_warn": "#E3B341",
    "text_main":   "#E6EDF3",
    "text_muted":  "#8B949E",
    "border":      "#30363D",
    "orb_idle":    "#00FFCC",
    "orb_think":   "#3FB950",
    "orb_listen":  "#FF3366",
}

class WorkerSignals(QObject):
    log_msg     = pyqtSignal(str, str)
    orb_state   = pyqtSignal(str)
    sys_stats   = pyqtSignal(int, int, int) 
    step_result = pyqtSignal(str, bool, str)
    vision_update = pyqtSignal(object) 
    hide_ui     = pyqtSignal()  
    show_ui     = pyqtSignal()

class ConfigManager:
    DEFAULTS = {
        "app_name":       "NEXUS AI CORE",
        "temperature":    0.2,
        "top_p":          0.9,
        "max_tokens":     512,
        "verify_actions": True,
        "max_retries":    3,
        "move_speed_min": 0.15,
        "move_speed_max": 0.35,
        "type_interval":  0.02,
        "noise_gate_db":  -40.0,
        "tts_voice":      "en-US-GuyNeural",
        "tts_rate":       "200",
        "tts_pitch":      "+0Hz",
        "whisper_model":  "base",
        "vision_max_w":   1280,
        "vision_max_h":   720,
        "safe_mode":      True,
        "monitor_count":  1,
        "monitor_layout": [],
        "known_apps":     {}
    }

    def __init__(self, filename: str = "ui_config.json"):
        self.filename = filename
        self.config = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    self.config.update(json.load(f))
            except Exception as e:
                logger.warning(f"Config load failed: {e}")

    def save(self):
        try:
            with open(self.filename, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Config save failed: {e}")

    def get(self, key, fallback=None):
        return self.config.get(key, fallback if fallback is not None else self.DEFAULTS.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()

class StepCard(QFrame):
    def __init__(self, label: str):
        super().__init__()
        self.setObjectName("StepCard")
        self.setStyleSheet(f"QFrame#StepCard {{ background-color: {PALETTE['bg_card']}; border: 1px solid {PALETTE['border']}; border-radius: 8px; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(20)
        self.dot.setStyleSheet("border: none; background: transparent; font-size: 14px;")

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {PALETTE['text_main']}; font-size: 12px; border: none; background: transparent;")

        self.detail = QLabel("")
        self.detail.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px; border: none; background: transparent;")

        self.timing = QLabel("")
        self.timing.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px; border: none; background: transparent;")

        layout.addWidget(self.dot)
        layout.addWidget(self.lbl)
        layout.addSpacing(8)
        layout.addWidget(self.detail)
        layout.addStretch()
        layout.addWidget(self.timing)

        self.set_status("pending")

    def set_status(self, status: str, detail: str = "", elapsed_ms: int = 0):
        colors = {"pending": PALETTE["text_muted"], "running": PALETTE["accent_warn"], "success": PALETTE["accent2"], "failed": PALETTE["accent_red"]}
        self.dot.setStyleSheet(f"color: {colors.get(status, PALETTE['text_muted'])}; border: none; background: transparent; font-size: 14px;")
        self.detail.setText(detail)
        if elapsed_ms: self.timing.setText(f"{elapsed_ms}ms")


class MonitorLayoutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.monitors = []
        self.bbox = None
        self.refresh_monitors()

    def refresh_monitors(self):
        try:
            import mss
            with mss.MSS() as sct:
                self.bbox = sct.monitors[0]
                self.monitors = sct.monitors[1:]
        except Exception as e:
            logger.warning(f"Could not load MSS for visualizer: {e}")
        self.update()

    def paintEvent(self, event):
        if not self.monitors or not self.bbox:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w_avail, h_avail = self.width() - 40, self.height() - 40
        if self.bbox["width"] == 0 or self.bbox["height"] == 0: return
        
        scale_w, scale_h = w_avail / self.bbox["width"], h_avail / self.bbox["height"]
        scale = min(scale_w, scale_h)
        
        off_x = (self.width() - (self.bbox["width"] * scale)) / 2
        off_y = (self.height() - (self.bbox["height"] * scale)) / 2

        for i, m in enumerate(self.monitors):
            x = int((m["left"] - self.bbox["left"]) * scale + off_x)
            y = int((m["top"] - self.bbox["top"]) * scale + off_y)
            mw, mh = int(m["width"] * scale), int(m["height"] * scale)
            
            rect = QRect(x, y, mw, mh)
            
            painter.setBrush(QColor("#A349A4") if i == 0 else QColor("#333333"))
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawRoundedRect(rect, 6, 6)
            
            painter.setPen(QColor("#FFFFFF"))
            font = painter.font()
            font.setPointSize(18)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(i + 1))


class SoftwareGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        
        self.current_chat_id = "default_chat"
        self.chats = {"default_chat": {"name": "Primary Session", "history": []}}
        
        self._agent_busy = False
        self._ptt_active = False
        self._abort_flag = False
        self._step_cards: list = []

        self.init_global_fonts()
        self._init_subsystems()

        self.signals = WorkerSignals()
        self.signals.log_msg.connect(self._append_log)
        self.signals.orb_state.connect(self.set_orb_state)
        self.signals.sys_stats.connect(self.update_hw_bars)
        self.signals.step_result.connect(self.on_step_result)
        self.signals.vision_update.connect(self.update_vision_preview)
        
        self.signals.hide_ui.connect(self.hide)
        self.signals.show_ui.connect(self.showNormal)

        self.init_ui()
        self._start_hw_monitor()
        self._start_orb_animation()
        self._start_vision_monitor()

        self._append_log("system", f"NEXUS online — {self.cfg.get('app_name')} ready.")

    def init_global_fonts(self):
        comic_font = QFont("Comic Sans MS", 10)
        QApplication.setFont(comic_font)

    def apply_dark_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {PALETTE['bg_deep']}; color: {PALETTE['text_main']}; }}
            QFrame {{ background-color: {PALETTE['bg_panel']}; border-radius: 8px; }}
            QPushButton {{ background-color: {PALETTE['bg_card']}; border: 1px solid {PALETTE['border']}; border-radius: 6px; padding: 8px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {PALETTE['accent']}; color: #000; }}
            QTextEdit, QLineEdit {{ background-color: {PALETTE['bg_input']}; border: 1px solid {PALETTE['border']}; border-radius: 6px; padding: 8px; }}
            QListWidget {{ background-color: {PALETTE['bg_input']}; border: 1px solid {PALETTE['border']}; border-radius: 6px; }}
            QListWidget::item {{ padding: 8px; border-bottom: 1px solid {PALETTE['border']}; }}
            QListWidget::item:selected {{ background-color: {PALETTE['accent']}; color: #000; font-weight: bold; }}
            QTabWidget::pane {{ border: 1px solid {PALETTE['border']}; border-radius: 6px; background-color: {PALETTE['bg_panel']}; }}
            QTabBar::tab {{ background-color: {PALETTE['bg_card']}; color: {PALETTE['text_muted']}; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
            QTabBar::tab:selected {{ background-color: {PALETTE['accent']}; color: #000; }}
            QGroupBox {{ border: 1px solid {PALETTE['border']}; border-radius: 6px; margin-top: 12px; padding-top: 12px; color: {PALETTE['accent']}; font-weight: bold; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }}
        """)

    def _init_subsystems(self):
        logger.info("Initializing Agent core architectures...")
        
        try:
            self.memory = AgentMemory()
        except Exception:
            self.memory = None

        try:
            vcfg = VoiceConfig()
            vcfg.tts_voice     = self.cfg.get("tts_voice")
            vcfg.tts_rate      = str(self.cfg.get("tts_rate"))
            vcfg.tts_pitch     = self.cfg.get("tts_pitch")
            vcfg.whisper_model = self.cfg.get("whisper_model")
            vcfg.noise_gate_db = self.cfg.get("noise_gate_db")
            self.voice_sys = VoiceSystem(vcfg)
        except Exception as e:
            logger.error(f"Voice core init failed: {e}")
            self.voice_sys = None

        try:
            cap_cfg = CaptureConfig()
            cap_cfg.max_width  = self.cfg.get("vision_max_w")
            cap_cfg.max_height = self.cfg.get("vision_max_h")
            self.vision_sys = DesktopVisionSystem(cap_cfg)
        except Exception as e:
            logger.error(f"Vision loop failed: {e}")
            self.vision_sys = None

        try:
            act_cfg = ActionConfig()
            act_cfg.move_duration_min = self.cfg.get("move_speed_min")
            act_cfg.move_duration_max = self.cfg.get("move_speed_max")
            act_cfg.type_interval     = self.cfg.get("type_interval")
            act_cfg.max_retries       = self.cfg.get("max_retries")

            def verifier(token: str) -> bool:
                if self.vision_sys:
                    frame = self.vision_sys.get_screen_frame(force=True)
                    return self.vision_sys.find_text_in_frame(token, frame)
                return True

            self.action_sys = InputAutomationSystem(
                voice_sys=self.voice_sys,
                config=act_cfg,
                verifier=verifier,
            )
        except Exception:
            self.action_sys = None
        
        try:
            self.brain_sys = LocalAgentBrain(
                memory=self.memory, 
                monitor_layout=self.cfg.get("monitor_layout", []),
                known_apps=self.cfg.get("known_apps", {})
            )
        except Exception:
            self.brain_sys = None

    def init_ui(self):
        self.setWindowTitle(self.cfg.get("app_name"))
        self.setGeometry(100, 100, 1300, 850)
        self.apply_dark_theme()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)

        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        sidebar_layout = QVBoxLayout(sidebar)
        
        self.app_name_label = QLabel(self.cfg.get("app_name"))
        self.app_name_label.setStyleSheet(f"color: {PALETTE['accent']}; font-size: 18px; font-weight: bold;")
        self.app_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(self.app_name_label)
        
        orb_row = QHBoxLayout()
        self.orb = QLabel("●")
        self.orb.setFixedSize(32, 32)
        self.orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb.setStyleSheet(f"color: {PALETTE['orb_idle']}; font-size: 26px; background: transparent;")
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(PALETTE["orb_idle"]))
        self.shadow.setOffset(0, 0)
        self.orb.setGraphicsEffect(self.shadow)
        self.orb_label = QLabel("IDLE")
        orb_row.addStretch()
        orb_row.addWidget(self.orb)
        orb_row.addWidget(self.orb_label)
        orb_row.addStretch()
        sidebar_layout.addLayout(orb_row)
        
        self.cpu_bar = QProgressBar()
        self.ram_bar = QProgressBar()
        self.gpu_bar = QProgressBar()
        
        bar_style = f"""
            QProgressBar {{ background-color: {PALETTE['bg_card']}; border: 1px solid {PALETTE['border']}; border-radius: 4px; text-align: center; font-size: 10px; }}
            QProgressBar::chunk {{ background-color: {PALETTE['accent2']}; border-radius: 3px; }}
        """
        self.cpu_bar.setStyleSheet(bar_style)
        self.ram_bar.setStyleSheet(bar_style.replace(PALETTE['accent2'], "#A349A4"))
        self.gpu_bar.setStyleSheet(bar_style.replace(PALETTE['accent2'], PALETTE['accent']))

        self.cpu_bar.setFormat("CPU %p%")
        self.ram_bar.setFormat("RAM %p%")
        self.gpu_bar.setFormat("GPU %p%")
        self.cpu_bar.setFixedHeight(14)
        self.ram_bar.setFixedHeight(14)
        self.gpu_bar.setFixedHeight(14)
        sidebar_layout.addWidget(self.cpu_bar)
        sidebar_layout.addWidget(self.ram_bar)
        sidebar_layout.addWidget(self.gpu_bar)
        
        sidebar_layout.addWidget(QLabel("CONVERSATIONS"))
        self.chat_list_widget = QListWidget()
        self.chat_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list_widget.customContextMenuRequested.connect(self.show_chat_context_menu)
        self.chat_list_widget.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list_widget)

        btn_new_chat = QPushButton("+ New Thread")
        btn_new_chat.clicked.connect(self.add_new_chat)
        sidebar_layout.addWidget(btn_new_chat)
        
        root_layout.addWidget(sidebar)

        workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget()
        
        # --- TAB A: COMMAND CENTER ---
        cmd_tab = QWidget()
        cmd_layout = QVBoxLayout(cmd_tab)
        
        top_bar = QHBoxLayout()
        model_label = QLabel("AI MODEL:")
        model_label.setStyleSheet(f"color: {PALETTE['text_muted']}; font-weight: bold; font-size: 11px;")
        
        self.model_combo = QComboBox()
        self.model_combo.setFixedWidth(200)
        self.model_combo.setStyleSheet(f"background-color: {PALETTE['bg_input']}; color: {PALETTE['accent']}; border: 1px solid {PALETTE['border']}; font-weight: bold;")
        if getattr(self, 'brain_sys', None) is not None:
            self.model_combo.addItems(self.brain_sys.get_available_models())
            self.model_combo.currentTextChanged.connect(self.brain_sys.set_model)
            
        clear_btn = QPushButton("Clear Output")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self._clear_history)
        
        top_bar.addWidget(model_label)
        top_bar.addWidget(self.model_combo)
        top_bar.addStretch()
        top_bar.addWidget(clear_btn)
        cmd_layout.addLayout(top_bar)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        cmd_layout.addWidget(self.chat_display)
        
        input_row = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Direct AI (e.g., 'edit this photo', 'book a trip', 'write a program')...")
        self.text_input.returnPressed.connect(self.send_text_command)
        
        self.ptt_btn = QPushButton("🎙 PTT")
        self.ptt_btn.pressed.connect(self.start_voice)
        self.ptt_btn.released.connect(self.stop_voice)
        
        self.send_btn = QPushButton("Execute")
        self.send_btn.clicked.connect(self.send_text_command)
        
        self.stop_btn = QPushButton("STOP PROCESS")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(f"background-color: {PALETTE['bg_card']}; color: {PALETTE['accent_red']}; border-color: {PALETTE['accent_red']};")
        self.stop_btn.clicked.connect(self.abort_process)

        input_row.addWidget(self.text_input, 1)
        input_row.addWidget(self.ptt_btn)
        input_row.addWidget(self.send_btn)
        input_row.addWidget(self.stop_btn)
        cmd_layout.addLayout(input_row)
        
        self.tabs.addTab(cmd_tab, "Command Center")
        
        # --- TAB B: LIVE VISION ---
        screen_tab = QWidget()
        screen_layout = QVBoxLayout(screen_tab)
        self.chk_vision_active = QCheckBox("Enable Live Screen Monitoring")
        self.chk_vision_active.setChecked(True)
        screen_layout.addWidget(self.chk_vision_active)
        
        self.lbl_screen_monitor = QLabel("Screen Preview")
        self.lbl_screen_monitor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_screen_monitor.setStyleSheet("background: #000; border: 1px solid #333;")
        self.lbl_screen_monitor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        screen_layout.addWidget(self.lbl_screen_monitor, 1)
        self.tabs.addTab(screen_tab, "Live Vision")

        self.tabs.addTab(self._build_training_page(), "Training & Memory")
        self.tabs.addTab(self._build_settings_page(), "System Settings")
        
        workspace_splitter.addWidget(self.tabs)

        timeline_widget = QWidget()
        timeline_layout = QVBoxLayout(timeline_widget)
        timeline_layout.addWidget(QLabel("Execution Timeline"))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._timeline_inner = QWidget()
        self._timeline_layout = QVBoxLayout(self._timeline_inner)
        self._timeline_layout.addStretch()
        scroll.setWidget(self._timeline_inner)
        timeline_layout.addWidget(scroll)
        
        workspace_splitter.addWidget(timeline_widget)
        workspace_splitter.setSizes([600, 250])
        
        root_layout.addWidget(workspace_splitter, 1)
        
        self.rebuild_chat_list_ui()

    def _start_vision_monitor(self):
        self.vision_timer = QTimer()
        self.vision_timer.timeout.connect(self._fetch_vision_frame)
        self.vision_timer.start(1000) 

    def _fetch_vision_frame(self):
        if not self.chk_vision_active.isChecked() or self._agent_busy:
            return
        threading.Thread(target=self._capture_and_emit, daemon=True).start()

    def _capture_and_emit(self):
        if getattr(self, 'vision_sys', None) is not None:
            try:
                frame = self.vision_sys.get_screen_frame(force=False)
                if frame is not None and frame.size > 0:
                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_image.shape
                    bytes_per_line = ch * w
                    qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    self.signals.vision_update.emit(qt_img)
            except Exception:
                pass

    @pyqtSlot(object)
    def update_vision_preview(self, qt_img):
        pixmap = QPixmap.fromImage(qt_img)
        scaled_pixmap = pixmap.scaled(self.lbl_screen_monitor.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.lbl_screen_monitor.setPixmap(scaled_pixmap)

    def rebuild_chat_list_ui(self):
        self.chat_list_widget.clear()
        for chat_id, data in self.chats.items():
            item = QListWidgetItem(data["name"])
            item.setData(Qt.ItemDataRole.UserRole, chat_id)
            self.chat_list_widget.addItem(item)
            if chat_id == self.current_chat_id:
                self.chat_list_widget.setCurrentItem(item)
        self.reload_chat_history_view()

    def on_chat_selected(self, item):
        self.current_chat_id = item.data(Qt.ItemDataRole.UserRole)
        self.reload_chat_history_view()

    def reload_chat_history_view(self):
        self.chat_display.clear()
        history = self.chats[self.current_chat_id]["history"]
        for sender, msg in history:
            color = PALETTE['accent'] if sender == "NEXUS" else PALETTE['text_main']
            self.chat_display.append(f"<b style='color:{color};'>{sender}:</b> {msg}<br>")

    def add_new_chat(self):
        chat_id = f"chat_{int(time.time())}"
        name, ok = QInputDialog.getText(self, "New Stream", "Enter chat name:")
        if ok and name.strip():
            self.chats[chat_id] = {"name": name.strip(), "history": []}
            self.current_chat_id = chat_id
            self.rebuild_chat_list_ui()

    def show_chat_context_menu(self, position):
        item = self.chat_list_widget.itemAt(position)
        if not item: return
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu()
        rename_action = QAction("Rename", self)
        delete_action = QAction("Delete", self)
        rename_action.triggered.connect(lambda: self.rename_chat_session(chat_id))
        delete_action.triggered.connect(lambda: self.delete_chat_session(chat_id))
        menu.addAction(rename_action)
        menu.addAction(delete_action)
        menu.exec(self.chat_list_widget.mapToGlobal(position))

    def rename_chat_session(self, chat_id):
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=self.chats[chat_id]["name"])
        if ok and new_name.strip():
            self.chats[chat_id]["name"] = new_name.strip()
            self.rebuild_chat_list_ui()

    def delete_chat_session(self, chat_id):
        if len(self.chats) <= 1: return
        del self.chats[chat_id]
        if self.current_chat_id == chat_id:
            self.current_chat_id = list(self.chats.keys())[0]
        self.rebuild_chat_list_ui()

    def log_to_active_chat(self, sender: str, text: str):
        self.chats[self.current_chat_id]["history"].append((sender, text))
        self.reload_chat_history_view()

    def _build_training_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        self.rule_list = QListWidget()
        self._reload_rule_list()
        layout.addWidget(QLabel("Behavioral Directives"))
        layout.addWidget(self.rule_list, 1)

        ctrl = QHBoxLayout()
        self.new_rule_input = QLineEdit()
        self.new_rule_input.setPlaceholderText("Add a rule...")
        self.rule_cat_combo = QComboBox()
        
        categories = getattr(AgentMemory, 'CATEGORIES', ["General", "System", "Safety"])
        self.rule_cat_combo.addItems(categories)
        
        self.rule_priority = QSpinBox()
        self.rule_priority.setRange(1, 10)
        self.rule_priority.setValue(5)
        
        inject_btn = QPushButton("Inject Rule")
        inject_btn.clicked.connect(self.add_training_rule)
        rem_btn = QPushButton("Remove")
        rem_btn.clicked.connect(self.remove_selected_rule)

        ctrl.addWidget(self.new_rule_input, 1)
        ctrl.addWidget(self.rule_cat_combo)
        ctrl.addWidget(self.rule_priority)
        ctrl.addWidget(inject_btn)
        ctrl.addWidget(rem_btn)
        layout.addLayout(ctrl)

        layout.addWidget(QLabel("Failure Logs"))
        self._fail_log = QTextEdit()
        self._fail_log.setReadOnly(True)
        self._reload_fail_log()
        layout.addWidget(self._fail_log, 1)

        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setSpacing(16)

        def group(title):
            g = QGroupBox(title)
            v = QVBoxLayout(g)
            return g, v

        def spin_row(layout_target, label, key, mn, mx, step, is_double=False):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            w = QDoubleSpinBox() if is_double else QSpinBox()
            if is_double:
                w.setDecimals(2)
                w.setSingleStep(step)
            w.setRange(mn, mx)
            w.setValue(self.cfg.get(key))
            w.valueChanged.connect(lambda v: self.cfg.set(key, v))
            row.addWidget(w)
            row.addStretch()
            layout_target.addLayout(row)

        g, v = group("AI SPATIAL MAPPING (WINDOWS TOPOLOGY)")
        info = QLabel("The AI maps mouse movements directly against the Windows OS coordinate system.\nIf displays are misaligned, click the button below to update them natively in Windows.")
        info.setStyleSheet("color: #8B949E; font-size: 11px;")
        v.addWidget(info)
        
        self.layout_visualizer = MonitorLayoutWidget()
        v.addWidget(self.layout_visualizer)
        
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("↻ Resync Layout")
        refresh_btn.clicked.connect(self.layout_visualizer.refresh_monitors)
        os_btn = QPushButton("🖥 Open Windows Display Settings")
        os_btn.setStyleSheet(f"background-color: {PALETTE['accent2']}; color: #000;")
        os_btn.clicked.connect(lambda: os.system("start ms-settings:display"))
        
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(os_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)
        layout.addWidget(g)

        g, v = group("AI INFERENCE & SAFETY")
        spin_row(v, "Temperature:", "temperature", 0, 1, 0.05, True)
        spin_row(v, "Max Tokens:", "max_tokens", 64, 4096, 64)
        spin_row(v, "Max Retries:", "max_retries", 1, 10, 1)
        spin_row(v, "Move Speed Min:", "move_speed_min", 0, 2, 0.05, True)
        
        chk = QCheckBox("Safe Mode (Confirm before clicking)")
        chk.setChecked(self.cfg.get("safe_mode"))
        chk.toggled.connect(lambda val: self.cfg.set("safe_mode", val))
        v.addWidget(chk)
        layout.addWidget(g)
        
        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _start_orb_animation(self):
        self._orb_timer = QTimer()
        self._orb_timer.timeout.connect(self._pulse_orb)
        self._orb_glow = 20
        self._orb_growing = True

    def _pulse_orb(self):
        self._orb_glow += 3 if self._orb_growing else -3
        if self._orb_glow >= 58: self._orb_growing = False
        elif self._orb_glow <= 12: self._orb_growing = True
        self.shadow.setBlurRadius(self._orb_glow)

    @pyqtSlot(str)
    def set_orb_state(self, state: str):
        state_map = {"idle": (PALETTE["orb_idle"], "IDLE"), "listening": (PALETTE["orb_listen"], "LISTENING"), "thinking": (PALETTE["orb_think"], "THINKING")}
        color, label = state_map.get(state, (PALETTE["orb_idle"], "IDLE"))
        self.shadow.setColor(QColor(color))
        self.orb.setStyleSheet(f"color: {color}; font-size: 26px; background: transparent;")
        self.orb_label.setText(label)
        if state in ("listening", "thinking"): self._orb_timer.start(30)
        else: self._orb_timer.stop(); self.shadow.setBlurRadius(20)

    def _start_hw_monitor(self):
        def _loop():
            while True:
                cpu = int(psutil.cpu_percent(interval=2))
                ram = int(psutil.virtual_memory().percent)
                gpu_load = 0
                try:
                    import GPUtil
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu_load = int(gpus[0].load * 100)
                except Exception:
                    pass
                self.signals.sys_stats.emit(cpu, ram, gpu_load)
        threading.Thread(target=_loop, daemon=True).start()

    @pyqtSlot(int, int, int)
    def update_hw_bars(self, cpu: int, ram: int, gpu: int):
        self.cpu_bar.setValue(cpu)
        self.ram_bar.setValue(ram)
        self.gpu_bar.setValue(gpu)

    @pyqtSlot(str, str)
    def _append_log(self, kind: str, text: str):
        if kind == "user": self.log_to_active_chat("YOU", text)
        elif kind == "nexus" or kind == "status": self.log_to_active_chat("NEXUS", text)
        elif kind == "error": self.log_to_active_chat("ERROR", text)
        else:
            self.chat_display.append(f"<i style='color:{PALETTE['text_muted']};'>[{kind}] {text}</i>")
        
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_history(self):
        self.chat_display.clear()
        if getattr(self, 'brain_sys', None) is not None:
            self.brain_sys.clear_history()
        self._append_log("system", "Chat history and context cleared.")

    def _add_step_card(self, label: str) -> StepCard:
        card = StepCard(label)
        count = self._timeline_layout.count()
        self._timeline_layout.insertWidget(count - 1, card)
        self._step_cards.append(card)
        return card

    def _clear_timeline(self):
        for card in self._step_cards:
            self._timeline_layout.removeWidget(card)
            card.deleteLater()
        self._step_cards = []

    @pyqtSlot(str, bool, str)
    def on_step_result(self, label: str, success: bool, detail: str):
        for card in self._step_cards:
            if card.lbl.text() == label:
                card.set_status("success" if success else "failed", detail)
                return

    def _reload_rule_list(self):
        if not hasattr(self, 'memory') or self.memory is None: return
        self.rule_list.clear()
        for r in getattr(self.memory, 'rules', []):
            self.rule_list.addItem(f"[{getattr(r, 'category', 'General')} | P{getattr(r, 'priority', 5)}] {getattr(r, 'text', '')}")

    def add_training_rule(self):
        if not hasattr(self, 'memory') or self.memory is None: return
        text = self.new_rule_input.text().strip()
        cat  = self.rule_cat_combo.currentText()
        pri  = self.rule_priority.value()
        if text:
            if hasattr(self.memory, 'add_rule'):
                self.memory.add_rule(text, category=cat, priority=pri)
            self._reload_rule_list()
            self.new_rule_input.clear()

    def remove_selected_rule(self):
        if not hasattr(self, 'memory') or self.memory is None: return
        item = self.rule_list.currentItem()
        if item:
            m = re.search(r"\] (.+)$", item.text())
            if m and hasattr(self.memory, 'remove_rule'):
                self.memory.remove_rule(m.group(1))
                self._reload_rule_list()

    def _reload_fail_log(self):
        if not hasattr(self, 'memory') or self.memory is None: return
        lines = []
        for e in getattr(self.memory, 'failure_log', [])[-30:]:
            ts = datetime.fromtimestamp(e.get("ts", time.time())).strftime("%m/%d %H:%M")
            lines.append(f"[{ts}] {e.get('error_type', 'Err')} | {e.get('instruction', '')[:40]}")
        self._fail_log.setPlainText("\n".join(lines))

    def start_voice(self):
        if self._agent_busy: return
        self._ptt_active = True
        self.ptt_btn.setText("🔴 REC")
        self.signals.orb_state.emit("listening")
        if getattr(self, 'voice_sys', None) is not None: 
            try: self.voice_sys.start_listening()
            except: pass

    def stop_voice(self):
        if not self._ptt_active: return
        self._ptt_active = False
        self.ptt_btn.setText("🎙 PTT")
        threading.Thread(target=self._process_audio, daemon=True).start()

    def _process_audio(self):
        if getattr(self, 'voice_sys', None) is not None:
            try:
                instruction = self.voice_sys.stop_listening_and_transcribe()
                if instruction: self._submit_command(instruction)
                else: self.signals.orb_state.emit("idle")
            except:
                self.signals.orb_state.emit("idle")

    def send_text_command(self):
        text = self.text_input.text().strip()
        if text:
            self.text_input.clear()
            self._submit_command(text)

    def _submit_command(self, instruction: str):
        if self._agent_busy: return
        self._abort_flag = False 
        self._clear_timeline()
        threading.Thread(target=self.run_ai_cycle, args=(instruction,), daemon=True).start()

    def abort_process(self):
        if self._agent_busy:
            self._abort_flag = True
            self.stop_btn.setText("ABORTING...")
            self._append_log("error", "Process Stop Intercepted! Aborting sequence.")

    def run_ai_cycle(self, instruction: str):
        self._agent_busy = True
        
        def ui_update_start():
            self.send_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.stop_btn.setStyleSheet(f"background-color: {PALETTE['bg_card']}; color: {PALETTE['accent_red']}; border-color: {PALETTE['accent_red']};")
        QTimer.singleShot(0, ui_update_start)
        
        self.signals.log_msg.emit("user", instruction)
        self.signals.orb_state.emit("thinking")
        start_ts = time.time()

        try:
            if self._abort_flag: raise InterruptedError("User Aborted")
            v_card = self._add_step_card("👁  Vision Setup")
            v_card.set_status("running")
            t0 = time.time()
            
            self.signals.hide_ui.emit()
            time.sleep(0.5) 
            
            frame = None
            if getattr(self, 'vision_sys', None) is not None:
                try: frame = self.vision_sys.get_screen_frame(force=True)
                except Exception as e: logger.error(f"Vision error: {e}")
            
            self.signals.show_ui.emit()
            
            v_card.set_status("success", "Captured", int((time.time() - t0) * 1000))

            if self._abort_flag: raise InterruptedError("User Aborted")
            i_card = self._add_step_card("🧠  AI Inference")
            i_card.set_status("running")
            t0 = time.time()
            
            inf_cfg = {"temperature": self.cfg.get("temperature"), "top_p": self.cfg.get("top_p"), "max_tokens": self.cfg.get("max_tokens")}
            
            raw_response = None
            if getattr(self, 'brain_sys', None) is not None:
                try: raw_response = self.brain_sys.decide_action(frame, instruction, inf_cfg)
                except Exception as e: logger.error(f"Inference error: {e}")
            else:
                raw_response = "COMMAND: chat('Brain subsystem is offline.')"
                
            elapsed_inf = int((time.time() - t0) * 1000)

            if not raw_response:
                i_card.set_status("failed", "No Response", elapsed_inf)
                raise Exception("Inference failed to return data.")
            i_card.set_status("success", f"{elapsed_inf}ms", elapsed_inf)

            # PARSE TAGS AND EXTRACT CONVERSATION
            thought = re.search(r"THOUGHT:(.*?)(?:VERIFY:|COMMAND:|$)", raw_response, re.DOTALL)
            command = re.search(r"COMMAND:(.*?)$", raw_response, re.DOTALL)
            
            if thought: 
                self.signals.log_msg.emit("thought", thought.group(1).strip())
            
            cmd_str = command.group(1).strip() if command else ""

            # Explicit check for conversational outputs
            if not cmd_str or cmd_str.lower() == "none":
                reply_text = thought.group(1).strip() if thought else raw_response
                self.signals.log_msg.emit("nexus", reply_text)
                if getattr(self, 'voice_sys', None) is not None:
                    self.voice_sys.speak(reply_text)
                
                e_card = self._add_step_card("✋  Executing")
                e_card.set_status("success", "Chat response", int((time.time() - t0) * 1000))
            else:
                if "chat(" in cmd_str.lower():
                    m = re.search(r"chat\(['\"](.*?)['\"]\)", cmd_str, re.IGNORECASE | re.DOTALL)
                    if m:
                        reply_text = m.group(1)
                        self.signals.log_msg.emit("nexus", reply_text)
                        if getattr(self, 'voice_sys', None) is not None:
                            self.voice_sys.speak(reply_text)

                if self._abort_flag: raise InterruptedError("User Aborted")
                e_card = self._add_step_card("✋  Executing")
                e_card.set_status("running")
                t0 = time.time()
                
                exec_result = {"success": False, "error": "Action Subsystem Offline"}
                if getattr(self, 'action_sys', None) is not None:
                    try: exec_result = self.action_sys.execute_action(cmd_str, instruction=instruction)
                    except Exception as e: exec_result["error"] = str(e)
                    
                elapsed_ex = int((time.time() - t0) * 1000)
                
                if exec_result.get("success", False):
                    e_card.set_status("success", cmd_str[:40], elapsed_ex)
                    if "chat(" not in cmd_str: self.signals.log_msg.emit("nexus", "Action executed.")
                else:
                    e_card.set_status("failed", "Execution Err", elapsed_ex)
                    self.signals.log_msg.emit("error", exec_result.get("error", "Error"))

        except InterruptedError:
            self._add_step_card("🛑  ABORTED").set_status("failed", "Process killed by user")
        except Exception as e:
            logger.error(f"Cycle exception: {e}")
            self.signals.log_msg.emit("error", f"System Error: {str(e)}")
        finally:
            self.signals.log_msg.emit("system", f"Cycle ended ({int((time.time() - start_ts) * 1000)}ms)")
            self.signals.orb_state.emit("idle")
            self._agent_busy = False
            
            def ui_update_end():
                self.send_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                self.stop_btn.setText("STOP PROCESS")
                self.stop_btn.setStyleSheet(f"background-color: {PALETTE['bg_card']}; color: {PALETTE['accent_red']}; border-color: {PALETTE['accent_red']};")
            QTimer.singleShot(0, ui_update_end)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    gui = SoftwareGUI()
    gui.show()
    sys.exit(app.exec())