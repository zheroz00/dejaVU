import os
import json
import shutil

# File name constants
LOG_FILE = 'activity_log.json'
PINNED_APPS_FILE = 'pinned_apps.json'
HOTKEY_SETTINGS_FILE = 'hotkey_settings.json'
WINDOW_STATE_FILE = 'window_state.json'
SETTINGS_FILE = 'settings.json'

def get_user_data_dir():
    """
    Returns the path to the user's data directory for the application.
    Creates it if it doesn't exist.
    """
    home = os.path.expanduser("~")
    # Use .dejavu folder in user home
    data_dir = os.path.join(home, ".dejavu")

    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir)
        except OSError:
            # Fallback to local dir if we can't write to home
            return os.path.abspath(".")

    return data_dir

def get_config_path(filename):
    """Get absolute path for a config file in the user data dir."""
    return os.path.join(get_user_data_dir(), filename)

def get_project_root():
    """Get the project root directory (where the script is run from)."""
    return os.path.abspath(".")

def migrate_settings_if_needed():
    """
    One-time migration from project root to ~/.dejavu.
    Copies settings files if they exist in project root but not in user data dir.
    """
    files_to_migrate = [
        LOG_FILE,
        PINNED_APPS_FILE,
        HOTKEY_SETTINGS_FILE,
        WINDOW_STATE_FILE,
    ]

    user_dir = get_user_data_dir()
    project_root = get_project_root()

    for filename in files_to_migrate:
        old_path = os.path.join(project_root, filename)
        new_path = os.path.join(user_dir, filename)

        # Only migrate if file exists in old location and not in new location
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                shutil.copy2(old_path, new_path)
                print(f"Migrated {filename} to {user_dir}")
            except Exception as e:
                print(f"Warning: Could not migrate {filename}: {e}")

    # Migrate API key from .env to settings.json
    _migrate_api_key_from_env()

def _migrate_api_key_from_env():
    """Migrate API key from .env file to settings.json if needed."""
    settings = get_settings()

    # If settings already has an API key, skip migration
    if settings.get('gemini_api_key'):
        return

    # Try to read from .env file
    env_path = os.path.join(get_project_root(), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('GEMINI_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                        if api_key and api_key != 'your_api_key_here':
                            settings['gemini_api_key'] = api_key
                            save_settings(settings)
                            print(f"Migrated API key from .env to settings.json")
                        break
        except Exception as e:
            print(f"Warning: Could not migrate API key from .env: {e}")

def get_settings():
    """Load settings from settings.json, return empty dict if not exists."""
    settings_path = get_config_path(SETTINGS_FILE)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_settings(settings):
    """Save settings to settings.json."""
    settings_path = get_config_path(SETTINGS_FILE)
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
    except IOError as e:
        print(f"Error saving settings: {e}")

def get_api_key():
    """
    Get API key from settings file, with fallback to environment variable
    for backward compatibility.
    """
    # First try settings file
    settings = get_settings()
    api_key = settings.get('gemini_api_key')

    if api_key:
        return api_key

    # Fallback to environment variable (for backward compatibility)
    return os.getenv("GEMINI_API_KEY")

def set_api_key(api_key):
    """Save API key to settings file."""
    settings = get_settings()
    settings['gemini_api_key'] = api_key
    save_settings(settings)
