"""
dejaVU - Launcher
Simple launcher that starts the integrated GUI application.
The .pyw extension means no console window will appear.
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.gui import ActivityApp, get_resource_path

if __name__ == "__main__":
    # Run the GUI - it now has the watcher built-in!
    app = QApplication(sys.argv)

    # Set application icon globally (for taskbar)
    icon_path = get_resource_path('dejavu.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = ActivityApp()
    window.show()
    sys.exit(app.exec())
