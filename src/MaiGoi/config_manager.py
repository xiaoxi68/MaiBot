import os
import toml
from pathlib import Path
from typing import Dict, Any

CONFIG_DIR = "config"
CONFIG_FILE = "gui_config.toml"
DEFAULT_CONFIG = {"adapters": []}


def get_config_path() -> Path:
    """Gets the full path to the config file."""
    # Assume script_dir is the project root for simplicity here
    # A more robust solution might involve finding the project root explicitly
    script_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
    config_path = script_dir / CONFIG_DIR / CONFIG_FILE
    return config_path


def load_config() -> Dict[str, Any]:
    """Loads the configuration from the TOML file."""
    config_path = get_config_path()
    print(f"[Config] Loading config from: {config_path}")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = toml.load(f)
                # Ensure essential keys exist, merge with defaults if necessary
                # For now, just check for 'adapters'
                if "adapters" not in config_data:
                    config_data["adapters"] = DEFAULT_CONFIG["adapters"]
                print("[Config] Config loaded successfully.")
                return config_data
        else:
            print("[Config] Config file not found, using default config.")
            # Save default config if file doesn't exist
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()  # Return a copy
    except FileNotFoundError:
        print("[Config] Config file not found (FileNotFoundError), using default config.")
        save_config(DEFAULT_CONFIG)  # Attempt to save default
        return DEFAULT_CONFIG.copy()
    except toml.TomlDecodeError as e:
        print(f"[Config] Error decoding TOML file: {e}. Using default config.")
        # Optionally: backup the corrupted file here
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"[Config] An unexpected error occurred loading config: {e}. Using default config.")
        import traceback

        traceback.print_exc()
        return DEFAULT_CONFIG.copy()


def save_config(config_data: Dict[str, Any]) -> bool:
    """Saves the configuration dictionary to the TOML file."""
    config_path = get_config_path()
    print(f"[Config] Saving config to: {config_path}")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        with open(config_path, "w", encoding="utf-8") as f:
            toml.dump(config_data, f)
        print("[Config] Config saved successfully.")
        return True
    except IOError as e:
        print(f"[Config] Error writing config file (IOError): {e}")
    except Exception as e:
        print(f"[Config] An unexpected error occurred saving config: {e}")
        import traceback

        traceback.print_exc()
    return False
