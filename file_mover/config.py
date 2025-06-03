from configparser import ConfigParser
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent / "config.ini"

DEFAULT_CONFIG = {
    "local_dir": "",                     # Source directory to monitor (required)
    "remote_dir": "",                    # Destination directory (required)
    "stability_wait": "5",               # Seconds to wait for file size to stabilize
    "scan_interval": "10",               # Seconds between directory scans
    "inactivity_threshold_minutes": "5", # Minutes before inactivity alert
    "pushover_app_token": "agsvfrtdcnc7iqqwhps89nrgmcya5a",  # Pushover application token
    "pushover_user_key": "",             # Pushover user key (required for notifications)
    "selected_devices": "",              # Comma separated list of device names
    "dry_run": "False",                  # Simulate moves without affecting files
    "file_filter": "",                   # Extension (e.g. ".txt") or regex if prefixed with "regex:"
    "progress_tracking_threshold_bytes": "52428800",  # 50MB - files larger than this show progress
    "verify_checksum": "False",          # Enable SHA256 checksum verification
    "health_notification_interval": "3600",  # Seconds between health check notifications
    "notification_rate_limit": "30",     # Minimum seconds between notifications
    "max_workers": "4"                   # Maximum concurrent file operations
}

class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass

def validate_config(config: ConfigParser) -> None:
    """Validate configuration values and raise exceptions for invalid settings"""
    section = config["FileMover"]
    
    # Required fields
    if not section.get("local_dir"):
        raise ConfigValidationError("local_dir is required")
    if not section.get("remote_dir"):
        raise ConfigValidationError("remote_dir is required")
    if not section.get("pushover_user_key"):
        logger.warning("pushover_user_key not set - notifications will be disabled")
    
    # Directory validation
    local_dir = Path(section["local_dir"]).expanduser()
    if not local_dir.exists():
        raise ConfigValidationError(f"Local directory does not exist: {local_dir}")
    if not local_dir.is_dir():
        raise ConfigValidationError(f"Local path is not a directory: {local_dir}")
    if not os.access(local_dir, os.R_OK):
        raise ConfigValidationError(f"No read access to local directory: {local_dir}")
    
    # Numeric validation
    try:
        stability_wait = int(section["stability_wait"])
        if stability_wait < 1:
            raise ConfigValidationError("stability_wait must be >= 1")
    except ValueError:
        raise ConfigValidationError("stability_wait must be a valid integer")
    
    try:
        scan_interval = int(section["scan_interval"])
        if scan_interval < 1:
            raise ConfigValidationError("scan_interval must be >= 1")
    except ValueError:
        raise ConfigValidationError("scan_interval must be a valid integer")
    
    try:
        max_workers = int(section["max_workers"])
        if max_workers < 1 or max_workers > 32:
            raise ConfigValidationError("max_workers must be between 1 and 32")
    except ValueError:
        raise ConfigValidationError("max_workers must be a valid integer")

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
