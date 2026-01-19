"""
Settings dialog for customizing hotkeys.
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QLineEdit, QScrollArea, QWidget,
                               QFrame, QMessageBox)
from PySide6.QtCore import Qt
from .hotkey_config import HotkeyConfig, HOTKEY_DESCRIPTIONS, format_hotkey_display


class HotkeySettingsDialog(QDialog):
    """Dialog for customizing application hotkeys."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hotkey Settings")
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        self.config = HotkeyConfig()
        self.hotkey_inputs = {}  # Maps action key to QLineEdit widget

        self.setup_ui()
        self.load_current_settings()

    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Header
        header = QLabel("Customize Hotkeys")
        header.setStyleSheet("font-size: 16pt; font-weight: bold; color: #78aaff;")
        layout.addWidget(header)

        # Instructions
        instructions = QLabel(
            "Enter hotkeys in the format: <ctrl>+<alt>+key\n"
            "Supported modifiers: <ctrl>, <alt>, <shift>, <win>\n"
            "Examples: <ctrl>+<alt>+space, <ctrl>+1, <shift>+f1"
        )
        instructions.setStyleSheet("font-size: 9pt; color: #a0a0a0; padding: 5px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Scroll area for hotkey entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)

        # Create input fields for each hotkey
        for action, description in HOTKEY_DESCRIPTIONS.items():
            hotkey_frame = self.create_hotkey_input(action, description)
            scroll_layout.addWidget(hotkey_frame)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        reset_button = QPushButton("Reset to Defaults")
        reset_button.setStyleSheet("""
            QPushButton {
                background-color: #cf6679;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e57888;
            }
        """)
        reset_button.clicked.connect(self.reset_to_defaults)

        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
        """)
        cancel_button.clicked.connect(self.reject)

        save_button = QPushButton("Save")
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #78aaff;
                color: #000000;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8bb8ff;
            }
        """)
        save_button.clicked.connect(self.save_settings)

        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)

        layout.addLayout(button_layout)

        # Dark mode styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: #e0e0e0;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

    def create_hotkey_input(self, action, description):
        """Create a single hotkey input field."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(5)

        # Description label
        label = QLabel(description)
        label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #e0e0e0;")

        # Input field
        input_field = QLineEdit()
        input_field.setPlaceholderText("Enter hotkey...")
        input_field.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 3px;
                padding: 6px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border-color: rgba(120, 170, 255, 0.7);
            }
        """)

        self.hotkey_inputs[action] = input_field

        layout.addWidget(label)
        layout.addWidget(input_field)

        return frame

    def load_current_settings(self):
        """Load current hotkey settings into the input fields."""
        for action, input_field in self.hotkey_inputs.items():
            hotkey_str = self.config.get(action)
            if hotkey_str:
                input_field.setText(hotkey_str)

    def reset_to_defaults(self):
        """Reset all hotkeys to default values."""
        reply = QMessageBox.question(
            self,
            "Reset Hotkeys",
            "Are you sure you want to reset all hotkeys to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.config.reset_to_defaults()
            self.load_current_settings()

    def save_settings(self):
        """Save the hotkey settings."""
        # Validate and save each hotkey
        for action, input_field in self.hotkey_inputs.items():
            hotkey_str = input_field.text().strip()

            if hotkey_str:
                # Basic validation - just check format
                if '+' not in hotkey_str:
                    QMessageBox.warning(
                        self,
                        "Invalid Hotkey",
                        f"Invalid hotkey format for '{HOTKEY_DESCRIPTIONS[action]}'.\n"
                        f"Expected format: <modifier>+key (e.g., <ctrl>+<alt>+space)"
                    )
                    return

                self.config.set(action, hotkey_str)
            else:
                # Allow empty hotkeys (disabled)
                self.config.set(action, "")

        QMessageBox.information(
            self,
            "Settings Saved",
            "Hotkey settings have been saved successfully!\n\n"
            "The new hotkeys will take effect immediately."
        )

        self.accept()
