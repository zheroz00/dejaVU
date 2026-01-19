import win32gui
import win32process
import psutil
import time
import json
import os
from .paths import get_config_path, LOG_FILE

LOG_FILE_PATH = get_config_path(LOG_FILE)
MAX_LOG_ENTRIES = 200
last_window = (None, None)

# Create log file if it doesn't exist
if not os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, 'w') as f:
        json.dump([], f)
    print(f"Created new activity_log.json file at {LOG_FILE_PATH}")
else:
    try:
        with open(LOG_FILE_PATH, 'r') as f:
            existing_log = json.load(f)
        print(f"Found existing log with {len(existing_log)} entries.")
    except json.JSONDecodeError:
        print("Log file corrupted, will start fresh.")
        with open(LOG_FILE_PATH, 'w') as f:
            json.dump([], f)

print("Starting window watcher... (Writing to activity_log.json)")
print("Press Ctrl+C to stop.")

try:
    while True:
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            process = psutil.Process(pid)
            exe_name = process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            exe_name = "unknown" 

        current_window = (window_title, exe_name)
        
        # Only log if it's a valid, non-empty window and has changed
        if window_title and current_window != last_window:

            # Create the log entry
            log_entry = {
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "title": window_title,
                "process": exe_name,
                "hwnd": hwnd
            }

            print(f"Logging: {window_title}") # Give feedback in terminal

            # Read the current log from disk (in case it was cleared by GUI)
            try:
                with open(LOG_FILE_PATH, 'r') as f:
                    activity_log = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # If file is corrupted or missing, start fresh
                activity_log = []

            # Add to the top of our list
            activity_log.insert(0, log_entry)

            # "Recycle" the list to keep it from growing forever
            if len(activity_log) > MAX_LOG_ENTRIES:
                # Trims the list to the 200 most recent entries
                activity_log = activity_log[:MAX_LOG_ENTRIES]

            # Save the log
            try:
                with open(LOG_FILE_PATH, 'w') as f:
                    json.dump(activity_log, f, indent=4)
            except IOError as e:
                print(f"Error writing to log file: {e}")

            last_window = current_window

        time.sleep(1)

except KeyboardInterrupt:
    print("\nWatcher stopped.")