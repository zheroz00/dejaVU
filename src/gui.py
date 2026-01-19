import sys
import json
import os
import win32gui
import win32process
import win32ui
import win32con
import win32api
import psutil
from collections import Counter
from datetime import datetime
import time
import logging

from PySide6.QtWidgets import (QApplication, QMainWindow, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget,
                               QLabel, QPushButton, QHBoxLayout, QCheckBox,
                               QFrame, QMessageBox, QFileDialog, QMenu, QDialog,
                               QSystemTrayIcon, QGraphicsDropShadowEffect, QSizePolicy, QScrollArea)
from PySide6.QtCore import QTimer, Qt, QSize, QThread, Signal, QPropertyAnimation, QEasingCurve, QPoint, QRect
from PySide6.QtGui import QCursor, QPixmap, QIcon, QImage, QBrush, QColor, QAction

# --- Import paths first and run migration before other imports ---
from .paths import (get_config_path, migrate_settings_if_needed,
                    LOG_FILE, PINNED_APPS_FILE, WINDOW_STATE_FILE,
                    get_settings, save_settings)
migrate_settings_if_needed()  # Must run before HotkeyManager import

# --- Import our "brain" ---
from . import llm_summarizer
from . import font
from .hotkey_manager import HotkeyManager
from .hotkey_settings_dialog import HotkeySettingsDialog
from . import blur_effect

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LOG_FILE_PATH = get_config_path(LOG_FILE)
PINNED_APPS_FILE_PATH = get_config_path(PINNED_APPS_FILE)
WINDOW_STATE_FILE_PATH = get_config_path(WINDOW_STATE_FILE)
MAX_RECENT_ITEMS = 50  # Load more for timeline grouping
MAX_LOG_ENTRIES = 200

# --- IGNORE LIST ---
IGNORE_TITLES = [
    "dejaVU",
    "Task Switching",
    "Program Manager",
]

# --- WINDOW STATES ---
SW_MAXIMIZE = 3
SW_RESTORE = 9

# --- CACHE ---
_icon_cache = {}

# --- UTILS ---
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_exe_path_from_hwnd(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0: return None
        process = psutil.Process(pid)
        return process.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
        return None

def get_app_icon(exe_path, size=48):
    if not exe_path or not os.path.exists(exe_path): return None
    cache_key = f"{exe_path}_{size}"
    if cache_key in _icon_cache: return _icon_cache[cache_key]

    try:
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)
        large, small = win32gui.ExtractIconEx(exe_path, 0)

        if large:
            hicon = large[0]
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
            hdc_mem = hdc.CreateCompatibleDC()
            hdc_mem.SelectObject(hbmp)
            hdc_mem.DrawIcon((0, 0), hicon)

            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format.Format_ARGB32)
            img = img.rgbSwapped()
            pixmap = QPixmap.fromImage(img).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            for icon in large: win32gui.DestroyIcon(icon)
            for icon in small: win32gui.DestroyIcon(icon)
            
            _icon_cache[cache_key] = pixmap
            return pixmap
    except Exception:
        pass

    try:
        icon = QIcon(exe_path)
        if not icon.isNull():
            pixmap = icon.pixmap(QSize(size, size))
            _icon_cache[cache_key] = pixmap
            return pixmap
    except Exception:
        pass
    return None

def get_relative_time(timestamp_str):
    try:
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        diff = now - timestamp
        seconds = diff.total_seconds()
        if seconds < 60: return "just now"
        elif seconds < 3600: return f"{int(seconds/60)}m ago"
        elif seconds < 86400: return f"{int(seconds/3600)}h ago"
        else: return f"{int(seconds/86400)}d ago"
    except Exception:
        return ""

# --- THEME & STYLES ---
COLORS = {
    'bg_glass': 'rgba(20, 20, 20, 0.85)',
    'card_bg': 'rgba(255, 255, 255, 0.05)',
    'card_hover': 'rgba(255, 255, 255, 0.09)',
    'card_active_border': 'rgba(120, 170, 255, 0.6)',
    'text_primary': '#ffffff',
    'text_secondary': '#aaaaaa',
    'accent': '#78aaff',
    'browser_accent': '#5ed4c8',  # Cyan/teal for browsers
    'border_subtle': 'rgba(255, 255, 255, 0.1)',
}

# Browser process names for color coding
BROWSER_PROCESSES = {'chrome.exe', 'firefox.exe', 'msedge.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe', 'iexplore.exe', 'safari.exe', 'comet.exe'}

def get_card_style(is_active=False, is_highlight=False):
    border_color = COLORS['card_active_border'] if is_highlight else COLORS['border_subtle']
    bg_color = "rgba(120, 170, 255, 0.1)" if is_highlight else COLORS['card_bg']
    
    return f"""
        QFrame {{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 8px;
        }}
        QFrame:hover {{
            background-color: {COLORS['card_hover']};
            border: 1px solid {COLORS['accent']};
        }}
    """

# --- WINDOW HIGHLIGHT ---
def highlight_window(hwnd):
    """Move the mouse cursor to the center of the target window - impossible to miss!"""
    try:
        import ctypes
        
        # Get window rectangle
        rect = win32gui.GetWindowRect(hwnd)
        x, y, right, bottom = rect
        
        # Calculate center of window
        center_x = (x + right) // 2
        center_y = (y + bottom) // 2
        
        # Move cursor to center of the window
        ctypes.windll.user32.SetCursorPos(center_x, center_y)
    except Exception:
        pass  # If it fails, no big deal


# --- COMPONENTS ---

class ContextCard(QFrame):
    clicked = Signal(object) # Emit self when clicked

    def __init__(self, index, parent=None, is_primary=False):
        super().__init__(parent)
        self.index = index
        self.is_primary = is_primary
        self.hwnd = None
        self.data_key = None
        
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(get_card_style())
        
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        
        # Icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.icon_label)
        
        # Text Info
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.title_label = QLabel("Empty")
        self.title_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: 500; font-size: 10pt; background: transparent; border: none;")
        text_layout.addWidget(self.title_label)
        
        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt; background: transparent; border: none;")
        text_layout.addWidget(self.sub_label)
        
        layout.addLayout(text_layout)
        
        if is_primary:
            # Add a subtle "Current" indicator or just make it bigger?
            # For now, the size and position in the deck implies importance
            pass

    def update_data(self, entry, is_active_app):
        if not entry:
            self.title_label.setText("Empty")
            self.sub_label.setText("")
            self.icon_label.clear()
            self.hwnd = None
            self.setEnabled(False)
            self.setStyleSheet(get_card_style(is_highlight=False))
            return

        self.setEnabled(True)
        self.hwnd = entry.get('hwnd')
        process = entry.get('process', 'Unknown')
        title = entry.get('normalized_title', 'Untitled')
        
        self.title_label.setText(title)
        self.sub_label.setText(process)

        # Style highlight if this card represents the currently active window
        self.setStyleSheet(get_card_style(is_highlight=is_active_app))
        
        # Icon
        exe_path = get_exe_path_from_hwnd(self.hwnd)
        icon = get_app_icon(exe_path, 32)
        if icon:
            self.icon_label.setPixmap(icon)
        else:
            self.icon_label.setText("⚡") # Fallback

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

class QuickDockItem(QLabel):
    clicked = Signal(object) # Emit self
    unpin_requested = Signal(object) # Emit self when user wants to unpin

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedSize(40, 40)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Empty Slot")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['card_bg']};
                border-radius: 8px;
                border: 1px solid {COLORS['border_subtle']};
            }}
            QLabel:hover {{
                background-color: {COLORS['card_hover']};
                border-color: {COLORS['accent']};
            }}
        """)
        self.pinned_data = None
        self.hwnd = None

    def update_data(self, pinned_item, active_window):
        self.pinned_data = pinned_item
        if pinned_item:
            self.hwnd = pinned_item.get('hwnd')
            self.setToolTip(f"{pinned_item.get('process')} - {pinned_item.get('title')}")
            
            # Icon
            exe_path = get_exe_path_from_hwnd(self.hwnd)
            icon = get_app_icon(exe_path, 32)
            if icon:
                self.setPixmap(icon)
            else:
                self.setText(pinned_item.get('process')[0].upper())
                
            # Highlight if active
            is_active = active_window and active_window.get('hwnd') == self.hwnd
            border = COLORS['accent'] if is_active else COLORS['border_subtle']
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {COLORS['card_bg']};
                    border-radius: 8px;
                    border: 1px solid {border};
                }}
                QLabel:hover {{
                    background-color: {COLORS['card_hover']};
                    border-color: {COLORS['accent']};
                }}
            """)
        else:
            self.clear()
            self.setText("➕")
            self.setToolTip("Empty Slot\nRight-click an item in history to pin.")
            self.hwnd = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        elif event.button() == Qt.MouseButton.RightButton:
            if self.pinned_data:
                menu = QMenu()
                unpin_action = menu.addAction("Unpin from Dock")
                action = menu.exec(event.globalPosition().toPoint())
                if action == unpin_action:
                    self.unpin_requested.emit(self)
        super().mousePressEvent(event)

class TimelineLog(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                /* Padding removed to avoid conflicts with setItemWidget */
                border-bottom: 1px solid {COLORS['border_subtle']};
            }}
            QListWidget::item:hover {{
                background: {COLORS['card_hover']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['card_bg']};
                border-left: 2px solid {COLORS['accent']};
            }}
        """)

class WatcherThread(QThread):
    def __init__(self):
        super().__init__()
        self.running = True
        self.last_window = (None, None)

    def run(self):
        if not os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, 'w') as f:
                json.dump([], f)

        while self.running:
            try:
                hwnd = win32gui.GetForegroundWindow()
                window_title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)

                try:
                    process = psutil.Process(pid)
                    exe_name = process.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    exe_name = "unknown"

                current_window = (window_title, exe_name)
                if window_title and current_window != self.last_window:
                    log_entry = {
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "title": window_title,
                        "process": exe_name,
                        "hwnd": hwnd
                    }
                    try:
                        with open(LOG_FILE_PATH, 'r') as f: activity_log = json.load(f)
                    except: activity_log = []

                    activity_log.insert(0, log_entry)
                    if len(activity_log) > MAX_LOG_ENTRIES:
                        activity_log = activity_log[:MAX_LOG_ENTRIES]

                    try:
                        with open(LOG_FILE_PATH, 'w') as f: json.dump(activity_log, f, indent=4)
                    except: pass

                    self.last_window = current_window
                time.sleep(1)
            except:
                time.sleep(1)

    def stop(self):
        self.running = False


class SummaryDialog(QDialog):
    """Styled dialog for displaying AI activity summaries."""

    def __init__(self, summary_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activity Summary")
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        # Dark theme styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #1a1a1a;
                color: {COLORS['text_primary']};
            }}
            QLabel {{
                color: {COLORS['text_primary']};
                font-size: 10pt;
                line-height: 1.6;
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QPushButton {{
                background-color: {COLORS['accent']};
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: #99bbff;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Format the summary text with proper spacing
        formatted_text = self._format_summary(summary_text)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QLabel(formatted_text)
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        content.setStyleSheet("padding: 10px;")

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setFixedWidth(100)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _format_summary(self, text):
        """Convert markdown-like text to HTML with proper spacing."""
        lines = text.split('\n')
        html_parts = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Headers (bold text between **)
            if line.startswith('**') and line.endswith('**'):
                header = line.strip('*')
                html_parts.append(f'<h3 style="color: {COLORS["accent"]}; margin-top: 16px; margin-bottom: 8px;">{header}</h3>')
            # Bullet points
            elif line.startswith('- '):
                content = line[2:]
                # Handle inline bold
                content = self._convert_bold(content)
                html_parts.append(f'<p style="margin: 8px 0 8px 16px;">• {content}</p>')
            # Regular text
            else:
                content = self._convert_bold(line)
                html_parts.append(f'<p style="margin: 8px 0;">{content}</p>')

        return ''.join(html_parts)

    def _convert_bold(self, text):
        """Convert **text** to <b>text</b>."""
        import re
        return re.sub(r'\*\*(.+?)\*\*', r'<b style="color: ' + COLORS['accent'] + r'">\1</b>', text)


class ActivityApp(QMainWindow):
    RESIZE_MARGIN = 8

    def __init__(self):
        super().__init__()
        self.setWindowTitle("dejaVU")
        self.resize(320, 700)
        self.setMinimumSize(280, 500)
        
        # Window Flags - load pin setting (default True)
        self._pin_enabled = get_settings().get('pin_window', True)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._pin_enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # State
        self._panel_visible = True
        self._resize_edge = None
        self._resize_start_pos = None
        self._drag_pos = None # For window dragging
        self._last_mod_time = 0
        self._last_screen_geo = None  # Track screen geometry for consistent show/hide
        self.pinned_apps = self.load_pinned_apps()
        
        # --- UI SETUP ---
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet(f"""
            #CentralWidget {{
                background-color: {COLORS['bg_glass']};
                border-radius: 12px;
                border: 1px solid {COLORS['border_subtle']};
            }}
        """)

        # Green glow effect
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(45)
        glow.setColor(QColor(50, 255, 120, 255))
        glow.setOffset(0, 0)
        self.central_widget.setGraphicsEffect(glow)

        self.setCentralWidget(self.central_widget)
        
        # Enable mouse tracking for custom resize
        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.central_widget.installEventFilter(self)
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)
        
        # 1. Header (Minimal)
        header_layout = QHBoxLayout()
        title = QLabel("dejaVU")
        title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: 600; letter-spacing: 1px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Settings Btn
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(f"background: transparent; color: {COLORS['text_secondary']}; border: none;")
        self.settings_btn.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_btn)
        
        main_layout.addLayout(header_layout)
        
        # 2. Context Deck (Top 3 recent contexts)
        self.deck_layout = QVBoxLayout()
        self.deck_layout.setSpacing(8)
        self.context_cards = []
        for i in range(3):
            # First card is primary (larger representation implied by position/logic)
            card = ContextCard(i, is_primary=(i==0))
            card.clicked.connect(self.on_card_clicked)
            self.context_cards.append(card)
            self.deck_layout.addWidget(card)
            
        main_layout.addLayout(self.deck_layout)
        
        # 3. Quick Dock (Pinned Apps)
        dock_label = QLabel("Quick Dock")
        dock_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt; font-weight: bold; text-transform: uppercase;")
        main_layout.addWidget(dock_label)
        
        self.dock_layout = QHBoxLayout()
        self.dock_layout.setSpacing(8)
        self.dock_items = []
        for i in range(4): # 4 Slots
            item = QuickDockItem(i)
            item.clicked.connect(self.on_dock_item_clicked)
            item.unpin_requested.connect(self.on_dock_item_unpin)
            self.dock_items.append(item)
            self.dock_layout.addWidget(item)
        self.dock_layout.addStretch()
        main_layout.addLayout(self.dock_layout)
        
        # 4. Timeline
        timeline_label = QLabel("Activity Timeline")
        timeline_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt; font-weight: bold; text-transform: uppercase;")
        main_layout.addWidget(timeline_label)
        
        self.timeline = TimelineLog()
        self.timeline.itemClicked.connect(self.on_timeline_clicked)
        # Enable context menu for pinning
        self.timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.timeline.customContextMenuRequested.connect(self.show_timeline_menu)
        main_layout.addWidget(self.timeline, stretch=1)
        
        # 5. Bottom Toolbar
        toolbar = QHBoxLayout()
        
        self.summarize_btn = QPushButton("Summarize")
        self.summarize_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: #000;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #8bb8ff; }}
        """)
        self.summarize_btn.clicked.connect(self.run_summarization)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{ background: {COLORS['card_hover']}; color: white; }}
        """)
        self.clear_btn.clicked.connect(self.clear_history)
        
        self.pin_check = QCheckBox("Pin")
        self.pin_check.setChecked(self._pin_enabled)
        self.pin_check.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.pin_check.stateChanged.connect(self.toggle_always_on_top)

        toolbar.addWidget(self.summarize_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.pin_check)
        main_layout.addLayout(toolbar)
        
        # Summary Display (Hidden by default, shown when needed or in overlay)
        # For this design, we'll popup a dialog or replace the timeline temporarily
        # Keeping it simple: separate dialog or message box for now
        
        # Threads & Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)
        
        self.watcher_thread = WatcherThread()
        self.watcher_thread.start()
        
        self.hotkey_manager = HotkeyManager(self)
        self.hotkey_manager.toggle_panel_triggered.connect(self.toggle_panel)
        self.hotkey_manager.cycle_history_triggered.connect(self.on_cycle_history)
        self.hotkey_manager.focus_card_triggered.connect(self.on_focus_card_hotkey)
        self.hotkey_manager.pinned_app_triggered.connect(self.on_pinned_app_hotkey)
        self.hotkey_manager.start()

        # State for cycling
        self.unique_contexts = []
        self.cycle_index = 0

        # Initial Position logic
        self._setup_slide_animation()
        self._setup_system_tray()
        
        # Load persisted state or default
        if not self._load_window_state():
            self._position_at_right_edge()

        # Run first update
        self.update_ui()
    
    # --- PERSISTENCE ---
    def _save_window_state(self):
        """Save window geometry and position."""
        state = {
            'geometry': self.geometry().getRect(), # x, y, w, h
            'visible': self._panel_visible
        }
        try:
            with open(WINDOW_STATE_FILE_PATH, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Failed to save window state: {e}")

    def _load_window_state(self):
        """Load window geometry from file. Returns True if successful."""
        active_screen = self.screen().availableGeometry()
        try:
            if os.path.exists(WINDOW_STATE_FILE_PATH):
                with open(WINDOW_STATE_FILE_PATH, 'r') as f:
                    state = json.load(f)
                
                rect = state.get('geometry')
                if rect and len(rect) == 4:
                    x, y, w, h = rect
                    # Ensure it's somewhat on screen
                    if x < active_screen.right() and y < active_screen.bottom():
                        self.setGeometry(x, y, w, h)
                        return True
        except Exception:
            pass
        return False
        
    def closeEvent(self, event):
        self._save_window_state()
        
        # Stop threads cleanly
        if hasattr(self, 'watcher_thread') and self.watcher_thread.isRunning():
            self.watcher_thread.stop()
            self.watcher_thread.wait(2000)  # Wait up to 2 seconds
        
        if hasattr(self, 'hotkey_manager'):
            self.hotkey_manager.stop()
        
        super().closeEvent(event)

    # --- MOUSE EVENTS FOR DRAGGING/RESIZING ---
    def mousePressEvent(self, event):
        """Handle mouse press for resize or drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                event.accept()
            else:
                # Native Dragging - smoother and supports Aero Snap
                self.releaseMouse()
                # Cast winId to int for pywin32
                hwnd = int(self.winId())
                
                # Release capture and send drag message
                win32gui.ReleaseCapture()
                # WM_NCLBUTTONDOWN = 0xA1, HTCAPTION = 0x2
                win32gui.SendMessage(hwnd, win32con.WM_NCLBUTTONDOWN, win32con.HTCAPTION, 0)
                
                # Note: valid resize events won't fire during native drag
                # We save state after interaction ends (handled via Enter/Leave or native events, 
                # but simplest is to just rely on closeEvent/hide saving, or hook into moveEvent)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for resize and cursor updates."""
        if self._resize_edge and event.buttons() == Qt.MouseButton.LeftButton:
            # Manual Resize (Native resize is harder to trigger programmatically properly with just hit tests)
            # Keeping manual resize as it allows cleaner edge control
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            min_w, min_h = self.minimumWidth(), self.minimumHeight()
            
            if 'left' in self._resize_edge:
                new_left = geo.left() + delta.x()
                new_width = geo.right() - new_left + 1
                if new_width >= min_w: geo.setLeft(new_left)
            if 'right' in self._resize_edge:
                geo.setRight(max(geo.left() + min_w, geo.right() + delta.x()))
            if 'top' in self._resize_edge:
                new_top = geo.top() + delta.y()
                new_height = geo.bottom() - new_top + 1
                if new_height >= min_h: geo.setTop(new_top)
            if 'bottom' in self._resize_edge:
                geo.setBottom(max(geo.top() + min_h, geo.bottom() + delta.y()))
            
            self.setGeometry(geo)
            event.accept()
            
        else:
            # Update cursor
            edge = self._get_resize_edge(event.pos())
            self._update_cursor_for_edge(edge)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle release, reset resizing state."""
        self._resize_edge = None
        self._resize_start_pos = None
        # _drag_pos is no longer used
        self.unsetCursor()
        
        # Save state
        self._save_window_state()
        super().mouseReleaseEvent(event)

    def _get_resize_edge(self, pos):
        """Determine resize edge (string based)."""
        rect = self.rect()
        x, y = pos.x(), pos.y()
        m = self.RESIZE_MARGIN
        
        left = x < m
        right = x > rect.width() - m
        top = y < m
        bottom = y > rect.height() - m
        
        if top and left: return 'top-left'
        if top and right: return 'top-right'
        if bottom and left: return 'bottom-left'
        if bottom and right: return 'bottom-right'
        if left: return 'left'
        if right: return 'right'
        if top: return 'top'
        if bottom: return 'bottom'
        return None

    def _update_cursor_for_edge(self, edge):
        """Update cursor."""
        cursors = {
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))


    # --- CORE UI LOGIC ---

    def update_ui(self):
        # 1. Load Data
        try:
            mod_time = os.path.getmtime(LOG_FILE_PATH)
            if mod_time == self._last_mod_time:
                # Still check active window for highlights even if log hasn't changed
                self.update_highlights()
                return

            self._last_mod_time = mod_time
            with open(LOG_FILE_PATH, 'r') as f:
                log_data = json.load(f)
        except:
            log_data = []

        active_window = self.get_current_active_window()
        
        # Filter ignores
        valid_data = [e for e in log_data if e['title'] not in IGNORE_TITLES]

        # 2. Update Context Deck (Unique Recent Contexts)
        # We need the last 3 *unique* applications/groups to allow switching back
        self.unique_contexts = []
        seen_keys = set()
        
        for entry in valid_data:
            kt = self.normalize_window_title(entry['title'], entry['process'])
            key = f"{entry['process']}::{kt}"
            if key not in seen_keys:
                # Add normalized title to entry for UI
                entry['normalized_title'] = kt
                self.unique_contexts.append(entry)
                seen_keys.add(key)
            if len(self.unique_contexts) >= 3:
                break
        
        for i, card in enumerate(self.context_cards):
            data = self.unique_contexts[i] if i < len(self.unique_contexts) else None
            # Check if this card represents the currently active window
            is_active_card = False
            if data and active_window:
                is_active_card = (data['hwnd'] == active_window['hwnd'])
            
            card.update_data(data, is_active_card)

        # 3. Update Quick Dock
        self.update_dock(active_window)

        # 4. Update Timeline (Grouped)
        self.update_timeline(valid_data, active_window)

    def update_dock(self, active_window):
        for i, item in enumerate(self.dock_items):
            pinned = self.pinned_apps[i] if i < len(self.pinned_apps) else None
            item.update_data(pinned, active_window)

    def update_timeline(self, data, active_window):
        self.timeline.clear()
        
        # Group by app sequentially
        grouped_history = []
        if not data: return

        current_group = None
        
        for entry in data[:MAX_RECENT_ITEMS]:
            process = entry['process']
            title = self.normalize_window_title(entry['title'], process)
            timestamp = entry['timestamp']
            
            if current_group and current_group['process'] == process and current_group['title'] == title:
                # Same activity, just update start time (since we read reverse chronologically)
                # Actually, the log is latest first. So the "start" of the group in UI terms is the latest entry.
                pass
            else:
                current_group = {
                    'process': process,
                    'title': title,
                    'timestamp': timestamp,
                    'hwnd': entry['hwnd'],
                    'full_title': entry['title']
                }
                grouped_history.append(current_group)

        for item_data in grouped_history:
            # Check if active
            is_active = active_window and item_data['hwnd'] == active_window['hwnd']
            
            display_text = f"{item_data['title']}"
            process_name = item_data['process']
            time_rel = get_relative_time(item_data['timestamp'])
            
            # Color based on app type (browser vs other)
            is_browser = process_name.lower() in BROWSER_PROCESSES
            title_color = COLORS['browser_accent'] if is_browser else COLORS['text_primary']
            
            # Formatting - vertical layout with title and process
            widget = QWidget()
            w_layout = QHBoxLayout(widget)
            w_layout.setContentsMargins(4, 4, 4, 4)
            w_layout.setSpacing(8)
            
            # Left side: app icon
            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setStyleSheet("background: transparent; border: none;")
            exe_path = get_exe_path_from_hwnd(item_data['hwnd'])
            icon = get_app_icon(exe_path, 24)
            if icon:
                icon_label.setPixmap(icon)
            else:
                icon_label.setText("⚡")
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w_layout.addWidget(icon_label)
            
            # Middle: title and process name stacked
            text_container = QWidget()
            text_layout = QVBoxLayout(text_container)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)
            
            lbl_title = QLabel(display_text)
            lbl_title.setStyleSheet(f"color: {title_color}; font-weight: {'bold' if is_active else 'normal'};")
            
            lbl_process = QLabel(process_name)
            lbl_process.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt;")
            
            text_layout.addWidget(lbl_title)
            text_layout.addWidget(lbl_process)
            
            # Right side: timestamp
            lbl_time = QLabel(time_rel)
            lbl_time.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt;")
            lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            w_layout.addWidget(text_container, stretch=1)
            w_layout.addWidget(lbl_time)
            
            l_item = QListWidgetItem()
            l_item.setSizeHint(QSize(0, 50))  # Slightly taller to fit process name
            l_item.setData(Qt.ItemDataRole.UserRole, item_data['hwnd'])
            l_item.setData(Qt.ItemDataRole.UserRole + 1, item_data)  # Store full data for pinning
            
            self.timeline.addItem(l_item)
            self.timeline.setItemWidget(l_item, widget)

    def update_highlights(self):
        # Lightweight update for active state only
        active = self.get_current_active_window()
        self.update_dock(active)
        # Context deck also needs update if active window changes, handled in full update_ui mostly
        # but could optimize here. For now, full update is cheap enough.

    # --- HELPERS ---
    def get_current_active_window(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid).name()
            return {'hwnd': hwnd, 'process': process}
        except:
            return None

    def normalize_window_title(self, title, process):
        if "Visual Studio Code" in title:
            parts = title.split(" - ")
            if len(parts) >= 2: return parts[1].strip()
        
        # Truncate
        if len(title) > 40: return title[:40] + "..."
        return title

    # --- ACTIONS ---
    def restore_window(self, hwnd):
        if not hwnd: return
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, SW_MAXIMIZE) # Or preserve state
            
            win32gui.SetForegroundWindow(hwnd)
            
            # Move cursor to window center so user can see which window was activated
            highlight_window(hwnd)
            
            # Reset cycle index on successful switch
            if hasattr(self, 'cycle_index'):
                self.cycle_index = 0
        except Exception as e:
            logger.error(f"Failed to restore window: {e}")

    def on_card_clicked(self, card):
        self.restore_window(card.hwnd)

    def on_dock_item_clicked(self, item):
        if item.hwnd:
            self.restore_window(item.hwnd)

    def on_dock_item_unpin(self, item):
        """Remove a pinned app from the dock."""
        if item.index < len(self.pinned_apps):
            del self.pinned_apps[item.index]
            self.save_pinned_apps()
            self.update_ui()

    def on_timeline_clicked(self, item):
        hwnd = item.data(Qt.ItemDataRole.UserRole)
        self.restore_window(hwnd)

    def show_timeline_menu(self, pos):
        item = self.timeline.itemAt(pos)
        if not item: return
        
        data = item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu()
        pin_action = menu.addAction("Pin App to Dock")
        action = menu.exec(self.timeline.mapToGlobal(pos))
        
        if action == pin_action:
            self.pin_app(data)

    def pin_app(self, data):
        if len(self.pinned_apps) >= 4:
            QMessageBox.warning(self, "Dock Full", "Max 4 pinned apps.")
            return
        
        new_pin = {
            'process': data['process'],
            'title': data['title'],
            'hwnd': data['hwnd']
        }
        self.pinned_apps.append(new_pin)
        self.save_pinned_apps()
        self.update_ui()

    def load_pinned_apps(self):
        try:
            if os.path.exists(PINNED_APPS_FILE_PATH):
                with open(PINNED_APPS_FILE_PATH, 'r') as f: return json.load(f)
        except: pass
        return []

    def save_pinned_apps(self):
        with open(PINNED_APPS_FILE_PATH, 'w') as f:
            json.dump(self.pinned_apps, f, indent=2)

    def run_summarization(self):
        self.summarize_btn.setText("Analyzing...")
        QApplication.processEvents()
        try:
            text = llm_summarizer.get_summary()
            dialog = SummaryDialog(text, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        self.summarize_btn.setText("Summarize")

    def clear_history(self):
        with open(LOG_FILE_PATH, 'w') as f: json.dump([], f)
        self.update_ui()

    def open_settings(self):
        dlg = HotkeySettingsDialog(self)
        if dlg.exec():
            self.hotkey_manager.reload_config()

    def toggle_always_on_top(self, state):
        flags = self.windowFlags()
        pinned = state == Qt.CheckState.Checked.value
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.update_blur()
        # Save setting
        settings = get_settings()
        settings['pin_window'] = pinned
        save_settings(settings)

    # --- WINDOW MANAGEMENT ESSENTIALS ---
    def eventFilter(self, obj, event):
        if obj == self.central_widget:
            if event.type() == event.Type.MouseMove: self.mouseMoveEvent(event)
            elif event.type() == event.Type.MouseButtonPress: self.mousePressEvent(event)
            elif event.type() == event.Type.MouseButtonRelease: self.mouseReleaseEvent(event)
        return super().eventFilter(obj, event)

    def _get_resize_edge(self, pos):
        rect = self.rect()
        x, y = pos.x(), pos.y()
        m = self.RESIZE_MARGIN
        left, right = x < m, x > rect.width() - m
        top, bottom = y < m, y > rect.height() - m
        
        if top and left: return 'top-left'
        if top and right: return 'top-right'
        if bottom and left: return 'bottom-left'
        if bottom and right: return 'bottom-right'
        if left: return 'left'
        if right: return 'right'
        if top: return 'top'
        if bottom: return 'bottom'
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                return
            
            # Only initiate drag if clicking on empty background area
            # Check if there's a child widget under the click position
            child = self.childAt(event.pos())
            # If clicking on central_widget directly (not a child of it), allow drag
            # If clicking on a button, card, or other interactive element, don't drag
            if child is None or child == self.central_widget:
                # Native Dragging - smoother and supports Aero Snap
                self.releaseMouse()
                hwnd = int(self.winId())
                win32gui.ReleaseCapture()
                # WM_NCLBUTTONDOWN = 0xA1, HTCAPTION = 0x2
                win32gui.SendMessage(hwnd, win32con.WM_NCLBUTTONDOWN, win32con.HTCAPTION, 0)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            min_w, min_h = self.minimumWidth(), self.minimumHeight()
            
            if 'left' in self._resize_edge:
                geo.setLeft(min(geo.right() - min_w, geo.left() + delta.x()))
            if 'right' in self._resize_edge:
                geo.setRight(max(geo.left() + min_w, geo.right() + delta.x()))
            if 'top' in self._resize_edge:
                geo.setTop(min(geo.bottom() - min_h, geo.top() + delta.y()))
            if 'bottom' in self._resize_edge:
                geo.setBottom(max(geo.top() + min_h, geo.bottom() + delta.y()))
            
            self.setGeometry(geo)
        else:
            edge = self._get_resize_edge(event.pos())
            cursors = {
                'left': Qt.CursorShape.SizeHorCursor, 'right': Qt.CursorShape.SizeHorCursor,
                'top': Qt.CursorShape.SizeVerCursor, 'bottom': Qt.CursorShape.SizeVerCursor,
                'top-left': Qt.CursorShape.SizeFDiagCursor, 'bottom-right': Qt.CursorShape.SizeFDiagCursor,
                'top-right': Qt.CursorShape.SizeBDiagCursor, 'bottom-left': Qt.CursorShape.SizeBDiagCursor
            }
            self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def update_blur(self):
        try:
             blur_effect.enable_blur(int(self.winId()), effect='acrylic', color=0x99141414)
        except: pass

    def showEvent(self, event):
        super().showEvent(event)
        self.update_blur()

    def _setup_system_tray(self):
        self.tray = QSystemTrayIcon(self)
        if hasattr(self, 'setWindowIcon'): self.tray.setIcon(self.windowIcon())
        menu = QMenu()
        menu.addAction("Toggle Details").triggered.connect(self.toggle_panel)
        menu.addAction("Exit").triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(lambda r: self.toggle_panel() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)

    def _quit_app(self):
        """Proper quit that triggers closeEvent for cleanup."""
        self.close()
        QApplication.quit()

    def toggle_panel(self):
        if self._panel_visible: self.hide_panel()
        else: self.show_panel()

    # --- ANIMATION & PANEL VISIBILITY ---

    def _setup_slide_animation(self):
        # Animation removed per user request to fix multi-monitor jumping issues
        pass

    def _position_at_right_edge(self):
        screen = self.screen().availableGeometry()
        self.move(screen.right() - self.width() - 20, screen.top() + 100)

    def hide_panel(self):
        if not self._panel_visible: return
        self._panel_visible = False
        self.hide()
        self._save_window_state()

    def show_panel(self):
        if self._panel_visible: return
        self._panel_visible = True
        
        # Restore position checks
        if not self.isVisible():
            self.show()
            
        self.raise_()
        self.activateWindow()
        self.update_blur()

    # --- HOTKEYS ---
    def on_cycle_history(self):
        """Cycle through recent unique contexts."""
        if not self.unique_contexts: return

        # Advance index
        self.cycle_index = (self.cycle_index + 1) % len(self.unique_contexts)
        
        # Get target window
        target = self.unique_contexts[self.cycle_index]
        if target and target.get('hwnd'):
            self.restore_window(target['hwnd'])

    def on_focus_card_hotkey(self, index):
        """Activate context card by index (0-2)."""
        if index < len(self.context_cards):
            card = self.context_cards[index]
            if card.hwnd:
                self.restore_window(card.hwnd)

    def on_pinned_app_hotkey(self, index):
        """Activate pinned app by index (0-3)."""
        if index < len(self.dock_items):
            item = self.dock_items[index]
            if item.hwnd:
                self.restore_window(item.hwnd)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Global Style
    app.setStyleSheet(f"""
        QToolTip {{ 
            background-color: {COLORS['bg_glass']}; 
            color: white; 
            border: 1px solid {COLORS['border_subtle']}; 
        }}
    """)
    
    icon_path = get_resource_path('dejavu.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    window = ActivityApp()
    window.show()
    sys.exit(app.exec())