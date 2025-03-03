from configparser import ConfigParser
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent / "config.ini"

DEFAULT_CONFIG = {
    "local_dir": "",
    "remote_dir": "",
    "stability_wait": "5",               # seconds to wait for file size to stabilize
    "scan_interval": "10",               # seconds between scans
    "inactivity_threshold_minutes": "5", # minutes before inactivity alert
    "pushover_app_token": "agsvfrtdcnc7iqqwhps89nrgmcya5a",  # kept as-is per instructions
    "pushover_user_key": "",
    "selected_devices": "",              # comma separated list
    "dry_run": "False",                  # simulate moves without affecting files
    "file_filter": "",                   # extension (e.g. ".txt") or regex if prefixed with "regex:"
    "progress_tracking_threshold_bytes": "52428800",
    "verify_checksum": "False",
    "health_notification_interval": "3600",
    "notification_rate_limit": "30",
    "max_bandwidth": "1048576",          # bytes per second (1MB/s default)
    "max_workers": "4"
}

def load_config() -> ConfigParser:
    config = ConfigParser()
    config["FileMover"] = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        config.read(CONFIG_FILE)
    return config

def save_config(config: ConfigParser) -> None:
    with CONFIG_FILE.open('w') as f:
        config.write(f)
    logger.info(f"Configuration saved to {CONFIG_FILE}")
