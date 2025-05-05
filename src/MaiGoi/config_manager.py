import toml

# Use tomlkit for dumping to preserve comments/formatting if needed,
# but stick to `toml` for loading unless specific features are required.
import tomlkit
from pathlib import Path
from typing import Dict, Any, Optional

CONFIG_DIR = Path("config")
# Define default filenames for different config types
CONFIG_FILES = {"gui": "gui_config.toml", "lpmm": "lpmm_config.toml", "bot": "bot_config.toml"}
DEFAULT_GUI_CONFIG = {"adapters": [], "theme": "System"}  # Add default theme


def get_config_path(config_type: str = "gui") -> Optional[Path]:
    """Gets the full path to the specified config file type."""
    filename = CONFIG_FILES.get(config_type)
    if not filename:
        print(f"[Config] Error: Unknown config type '{config_type}'")
        return None

    # Determine the base directory relative to this file
    # Assumes config_manager.py is in src/MaiGoi/
    try:
        script_dir = Path(__file__).parent.parent.parent  # Project Root (MaiBot-Core/)
        config_path = script_dir / CONFIG_DIR / filename
        return config_path
    except Exception as e:
        print(f"[Config] Error determining config path for type '{config_type}': {e}")
        return None


def load_config(config_type: str = "gui") -> Dict[str, Any]:
    """Loads the configuration from the specified TOML file type."""
    config_path = get_config_path(config_type)
    if not config_path:
        return {}  # Return empty dict if path is invalid

    print(f"[Config] Loading {config_type} config from: {config_path}")
    default_config_to_use = DEFAULT_GUI_CONFIG if config_type == "gui" else {}

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                # Use standard toml for loading, it's generally more robust
                config_data = toml.load(f)
                print(f"[Config] {config_type} config loaded successfully.")
                # Basic check for GUI config default keys
                if config_type == "gui":
                    if "adapters" not in config_data:
                        config_data["adapters"] = DEFAULT_GUI_CONFIG["adapters"]
                    if "theme" not in config_data:
                        config_data["theme"] = DEFAULT_GUI_CONFIG["theme"]
                return config_data
        else:
            print(f"[Config] {config_type} config file not found, using default.")
            # Save default config only if it's the GUI config
            if config_type == "gui":
                save_config(default_config_to_use, config_type=config_type)
            return default_config_to_use.copy()  # Return a copy
    except FileNotFoundError:
        print(f"[Config] {config_type} config file not found (FileNotFoundError), using default.")
        if config_type == "gui":
            save_config(default_config_to_use, config_type=config_type)  # Attempt to save default
        return default_config_to_use.copy()
    except toml.TomlDecodeError as e:
        print(f"[Config] Error decoding {config_type} TOML file: {e}. Using default.")
        return default_config_to_use.copy()
    except Exception as e:
        print(f"[Config] An unexpected error occurred loading {config_type} config: {e}.")
        import traceback

        traceback.print_exc()
        return default_config_to_use.copy()


def save_config(config_data: Dict[str, Any], config_type: str = "gui") -> bool:
    """Saves the configuration dictionary to the specified TOML file type."""
    config_path = get_config_path(config_type)
    if not config_path:
        return False  # Cannot save if path is invalid

    print(f"[Config] Saving {config_type} config to: {config_path}")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        with open(config_path, "w", encoding="utf-8") as f:
            # Use tomlkit.dump if preserving format/comments is important
            # Otherwise, stick to toml.dump for simplicity
            tomlkit.dump(config_data, f)  # Using tomlkit here
        print(f"[Config] {config_type} config saved successfully.")
        return True
    except IOError as e:
        print(f"[Config] Error writing {config_type} config file (IOError): {e}")
    except Exception as e:
        print(f"[Config] An unexpected error occurred saving {config_type} config: {e}")
        import traceback

        traceback.print_exc()
    return False
