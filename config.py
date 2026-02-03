"""Configuration settings for the chess screen watcher."""

import os
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".chess_watcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
STOCKFISH_DIR = CONFIG_DIR / "stockfish"

DEFAULT_CONFIG = {
    "stockfish_path": None,
    "analysis_depth": 15,
    "capture_interval_ms": 500,
    "board_region": None,  # {"x": int, "y": int, "width": int, "height": int}
    "board_flipped": False,  # True if playing as black
    "theme": "auto",  # auto, chess_com, lichess
}


def ensure_config_dir():
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STOCKFISH_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load configuration from file."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            saved = json.load(f)
            # Merge with defaults to handle new config options
            config = DEFAULT_CONFIG.copy()
            config.update(saved)
            return config
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration to file."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def find_stockfish():
    """Try to find Stockfish executable."""
    config = load_config()

    # Check saved path
    if config["stockfish_path"] and Path(config["stockfish_path"]).exists():
        return config["stockfish_path"]

    # Common locations on Windows
    common_paths = [
        STOCKFISH_DIR / "stockfish-windows-x86-64-avx2.exe",
        STOCKFISH_DIR / "stockfish.exe",
        Path("C:/stockfish/stockfish.exe"),
        Path("C:/Program Files/Stockfish/stockfish.exe"),
        Path("C:/Program Files (x86)/Stockfish/stockfish.exe"),
    ]

    for path in common_paths:
        if path.exists():
            config["stockfish_path"] = str(path)
            save_config(config)
            return str(path)

    # Try PATH
    import shutil
    stockfish_in_path = shutil.which("stockfish")
    if stockfish_in_path:
        config["stockfish_path"] = stockfish_in_path
        save_config(config)
        return stockfish_in_path

    return None
