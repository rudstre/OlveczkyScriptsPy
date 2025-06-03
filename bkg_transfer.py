import os
import time
import shutil
import json
import requests
import logging
import multiprocessing
import argparse
from pushover import init, Client
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("file_mover/file_mover.log")
    ]
)
logger = logging.getLogger("FileMover")

# Default configuration
DEFAULT_CONFIG = {
    "local_dir": "",
    "remote_dir": "",
    "stability_wait": 5,
    "scan_interval": 10,
    "inactivity_threshold_minutes": 5,
    "pushover_app_token": "agsvfrtdcnc7iqqwhps89nrgmcya5a",
    "pushover_user_key": "",
    "selected_devices": []
}

# Config file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    """Load configuration from file or create default if not exists."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Update with any missing default keys
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as error:
            logger.error(f"Error loading config file: {error}")
            return DEFAULT_CONFIG.copy()
    else:
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration to file."""
    try:
        # Create a serializable copy of the config
        serializable_config = {}
        for key, value in config.items():
            serializable_config[key] = value
        with open(CONFIG_FILE, 'w') as f:
            json.dump(serializable_config, f, indent=4)
        logger.info(f"Configuration saved to {CONFIG_FILE}")
    except Exception as error:
        logger.error(f"Error saving config file: {error}")


def file_is_stable(filepath, wait_time):
    """Check if a file's size remains unchanged over wait_time seconds."""
    try:
        initial_size = os.path.getsize(filepath)
        if initial_size == 0:
            return False  # Skip empty files
        time.sleep(wait_time)
        later_size = os.path.getsize(filepath)
        return initial_size == later_size
    except OSError as error:
        logger.error(f"Error checking stability for {filepath}: {error}")
        return False


def move_func(src, dest, q):
    """Top-level helper function for moving a file."""
    try:
        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        q.put("success")
    except Exception as error:
        q.put(error)


def safe_move_file(src, dest, timeout=60):
    """
    Move a file from src to dest in a separate process.
    If the move does not complete within 'timeout' seconds, raise a TimeoutError.
    """
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=move_func, args=(src, dest, q))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join()
        raise TimeoutError(f"Moving file {src} to {dest} timed out after {timeout} seconds")
    result = q.get()
    if result != "success":
        raise result
    return True


def move_completed_files(local_dir, remote_dir, stability_wait, client, selected_devices):
    """
    For each file in local_dir that is stable, attempt to move it to remote_dir.
    If the move fails, send a notification to each selected device.
    Returns the number of files moved and the number of errors.
    """
    moved_files = 0
    errors = 0

    for filename in os.listdir(local_dir):
        src_path = os.path.join(local_dir, filename)
        if os.path.isfile(src_path) and file_is_stable(src_path, stability_wait):
            dest_path = os.path.join(remote_dir, filename)

            # Check if destination file already exists
            if os.path.exists(dest_path):
                error_message = f"Destination file already exists: {dest_path}"
                logger.warning(error_message)
                notify_devices(client, selected_devices, error_message, title="File Already Exists")
                continue

            try:
                logger.info(f"Moving {filename}...")
                safe_move_file(src_path, dest_path, timeout=60)
                logger.info(f"Successfully moved {filename} to {remote_dir}")
                moved_files += 1
            except Exception as move_error:
                error_message = f"Error moving {filename}: {move_error}"
                logger.error(error_message)
                notify_devices(client, selected_devices, error_message, title="File Move Error")
                errors += 1

    if moved_files > 0 or errors > 0:
        return moved_files, errors, f"Moved {moved_files} files with {errors} errors"
    return 0, 0, None


def get_devices(app_token, user_key):
    """
    Retrieve the list of devices using the Pushover validate endpoint.
    """
    try:
        url = "https://api.pushover.net/1/users/validate.json"
        payload = {"token": app_token, "user": user_key}
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 1:
            return data.get("devices", [])
        logger.error(f"API returned status {data.get('status')}: {data.get('errors', ['Unknown error'])}")
        return []
    except requests.exceptions.RequestException as api_error:
        logger.error(f"Failed to retrieve devices: {api_error}")
        return []


def notify_devices(client, devices, message, title="Notification"):
    """
    Send the specified message to each device in devices.
    """
    if not devices:
        logger.warning(f"No devices specified for notification: {title}")
        return

    try:
        for device in devices:
            client.send_message(message, title=title, device=device)
        logger.info(f"Notification sent to {len(devices)} devices: {title}")
    except Exception as notify_error:
        logger.error(f"Failed to send notification: {notify_error}")


def validate_directory(directory_path):
    """Validate that a directory exists and is accessible."""
    path = Path(directory_path).expanduser().resolve()
    if not path.exists():
        return False, f"Directory does not exist: {path}"
    if not path.is_dir():
        return False, f"Path is not a directory: {path}"
    if not os.access(path, os.R_OK | os.W_OK):
        return False, f"Directory is not readable/writable: {path}"
    return True, str(path)


def setup_config():
    """Interactive setup to create or update configuration."""
    config = load_config()

    print("=" * 60)
    print("File Mover Configuration Setup")
    print("=" * 60)
    print("Press Enter to keep current values shown in [brackets]")
    print("-" * 60)

    # Local directory
    default = config["local_dir"] if config["local_dir"] else "Not set"
    local_dir = input(f"Local directory where files are being saved [{default}]: ").strip()
    if local_dir:
        valid, message = validate_directory(local_dir)
        if not valid:
            print(f"Error: {message}")
            return None
        config["local_dir"] = message
    elif not config["local_dir"]:
        print("Error: Local directory is required")
        return None

    # Remote directory
    default = config["remote_dir"] if config["remote_dir"] else "Not set"
    remote_dir = input(f"Remote folder to move files to [{default}]: ").strip()
    if remote_dir:
        valid, message = validate_directory(remote_dir)
        if not valid:
            print(f"Error: {message}")
            return None
        config["remote_dir"] = message
    elif not config["remote_dir"]:
        print("Error: Remote directory is required")
        return None

    # Stability wait time
    default = config["stability_wait"]
    stability_wait = input(f"Wait time (seconds) to check if a file is stable [{default}]: ").strip()
    if stability_wait:
        try:
            # Convert to float first to handle decimal input
            value = int(stability_wait)
            if value <= 0:
                print("Error: Wait time must be positive")
                return None
            config["stability_wait"] = value
        except ValueError:
            print("Error: Invalid number")
            return None

    # Scan interval
    default = config["scan_interval"]
    scan_interval = input(f"Scan interval (seconds) for checking the directory [{default}]: ").strip()
    if scan_interval:
        try:
            # Convert to float first to handle decimal input
            value = int(scan_interval)
            if value <= 0:
                print("Error: Scan interval must be positive")
                return None
            config["scan_interval"] = value
        except ValueError:
            print("Error: Invalid number")
            return None

    # Inactivity threshold
    default = config["inactivity_threshold_minutes"]
    inactivity = input(f"Minutes of inactivity before warning [{default}]: ").strip()
    if inactivity:
        try:
            # Convert to float first to handle decimal input
            value = int(inactivity)
            if value <= 0:
                print("Error: Inactivity threshold must be positive")
                return None
            config["inactivity_threshold_minutes"] = value
        except ValueError:
            print("Error: Invalid number")
            return None

    # Pushover user key
    default = config["pushover_user_key"] if config["pushover_user_key"] else "Not set"
    user_key = input(f"Pushover User Key (login to pushover.net) [{default}]: ").strip()
    if user_key:
        config["pushover_user_key"] = user_key
    elif not config["pushover_user_key"]:
        print("Error: Pushover User Key is required")
        return None

    # Pushover API key
    default = config["pushover_app_token"]
    app_token = input(f"Pushover app token [{default}]: ").strip()
    if app_token:
        config["pushover_app_token"] = app_token
    try:
        app_token = config["pushover_app_token"]
        init(app_token)
        client = Client(config["pushover_user_key"])

        if not client.verify():
            print("Error: Failed to verify Pushover credentials")
            return None

        devices = get_devices(app_token, config["pushover_user_key"])
        if not devices:
            print("Error: No devices found for this account")
            return None
    except Exception as push_error:
        print(f"Error: Pushover initialization failed: {push_error}")
        return None

    # Device selection
    print("\nDevices associated with your account:")
    for idx, device in enumerate(devices):
        print(f"  {idx + 1}. {device}")

    current_devices = config["selected_devices"]
    if current_devices:
        print(f"Currently selected: {', '.join(current_devices)}")

    selection = input("Enter the number(s) of the device(s) to use (comma separated, or 'all'): ").strip()

    if selection:
        if selection.lower() == 'all':
            config["selected_devices"] = devices
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_devices = [devices[i] for i in indices if 0 <= i < len(devices)]
                if not selected_devices:
                    print("Error: No valid devices selected")
                    return None
                config["selected_devices"] = selected_devices
            except Exception as selection_error:
                print(f"Error: Invalid selection: {selection_error}")
                return None
    elif not config["selected_devices"]:
        print("Error: Device selection is required")
        return None

    # Save configuration
    save_config(config)
    print("\nConfiguration updated successfully!")
    return config


def run_with_config(config):
    """Run the file mover with the provided configuration."""

    # Validate directories again just to be safe
    local_valid, local_message = validate_directory(config["local_dir"])
    if not local_valid:
        logger.error(local_message)
        return

    remote_valid, remote_message = validate_directory(config["remote_dir"])
    if not remote_valid:
        logger.error(remote_message)
        return

    # Extract config values
    local_dir = config["local_dir"]
    remote_dir = config["remote_dir"]
    stability_wait = config["stability_wait"]
    scan_interval = config["scan_interval"]
    inactivity_threshold_minutes = config["inactivity_threshold_minutes"]
    inactivity_threshold_seconds = inactivity_threshold_minutes * 60
    app_token = config["pushover_app_token"]
    user_key = config["pushover_user_key"]
    selected_devices = config["selected_devices"]

    # Initialize Pushover
    try:
        init(app_token)
        client = Client(user_key)
        if not client.verify():
            logger.error("Failed to verify Pushover credentials")
            return
    except Exception as push_error:
        logger.error(f"Pushover initialization error: {push_error}")
        return

    print("=" * 60)
    print("File Mover with Pushover Notifications")
    print("=" * 60)
    print(f"Monitoring '{local_dir}' and moving files to '{remote_dir}'")
    print(f"Scan interval: {scan_interval} seconds")
    print(f"Stability wait: {stability_wait} seconds")
    print(f"Inactivity alert: {inactivity_threshold_minutes} minutes")
    print(f"Pushover devices: {', '.join(selected_devices)}")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print()

    # Send startup notification
    notify_devices(
        client,
        selected_devices,
        f"File Mover started. Monitoring {local_dir} and moving files to {remote_dir}.",
        title="File Mover Started"
    )

    disconnected = False
    reconnect_attempts = 0
    last_file_time = datetime.now()  # Track the last time a file was moved successfully
    inactivity_notified = False  # Track if we've already sent an inactivity notification

    # --- Main monitoring loop ---
    try:
        while True:
            if not disconnected:
                local_valid, _ = validate_directory(local_dir)
                remote_valid, _ = validate_directory(remote_dir)

                if not local_valid:
                    message = f"Error: Local directory ({local_dir}) is no longer accessible."
                    logger.error(message)
                    notify_devices(client, selected_devices, message, title="Local Disconnect")
                    disconnected = True
                    reconnect_attempts = 0
                    continue

                if not remote_valid:
                    message = f"Error: Remote directory ({remote_dir}) is no longer accessible."
                    logger.error(message)
                    notify_devices(client, selected_devices, message, title="Remote Disconnect")
                    disconnected = True
                    reconnect_attempts = 0
                    continue

                moved, errors, result = move_completed_files(local_dir, remote_dir, stability_wait, client,
                                                             selected_devices)

                # If files were moved, update the last file time and reset notification flag
                if moved > 0:
                    last_file_time = datetime.now()
                    inactivity_notified = False

                if result:
                    logger.info(result)

                # Check for inactivity
                time_since_last_file = datetime.now() - last_file_time
                if (time_since_last_file.total_seconds() > inactivity_threshold_seconds and
                        not inactivity_notified):
                    elapsed_minutes = time_since_last_file.total_seconds() / 60
                    message = (f"Warning: No files transferred for {elapsed_minutes:.1f} minutes. "
                               f"Last file was at {last_file_time.strftime('%H:%M:%S')}. "
                               f"Recording may have stopped.")
                    logger.warning(message)
                    notify_devices(client, selected_devices, message, title="Inactivity Warning")
                    inactivity_notified = True

            else:  # We're in disconnected state
                reconnect_attempts += 1
                local_valid, _ = validate_directory(local_dir)
                remote_valid, _ = validate_directory(remote_dir)

                if local_valid and remote_valid:
                    message = f"Directories reconnected after {reconnect_attempts} attempts."
                    logger.info(message)
                    notify_devices(client, selected_devices, message, title="Reconnection")
                    disconnected = False
                    # Reset inactivity timer when reconnected
                    last_file_time = datetime.now()
                    inactivity_notified = False
                elif reconnect_attempts % 10 == 0:  # Notify every 10 attempts
                    message = f"Still disconnected after {reconnect_attempts} attempts."
                    logger.warning(message)
                    notify_devices(client, selected_devices, message, title="Still Disconnected")

            time.sleep(scan_interval)

    except KeyboardInterrupt:
        message = "File Mover stopped by user."
        logger.info(message)
        notify_devices(client, selected_devices, message, title="File Mover Stopped")
    except Exception as main_error:
        message = f"File Mover crashed: {main_error}"
        logger.critical(message)
        notify_devices(client, selected_devices, message, title="File Mover Error")


def main():
    """Main entry point with command line argument handling."""
    parser = argparse.ArgumentParser(description="File Mover with Pushover Notifications")
    parser.add_argument(
        "--setup", action="store_true",
        help="Run the setup wizard to configure the application"
    )
    parser.add_argument(
        "--run", action="store_true",
        help="Run using the saved configuration"
    )

    args = parser.parse_args()

    # If no arguments provided, show setup if no config exists, otherwise run
    if not args.setup and not args.run:
        if os.path.exists(CONFIG_FILE):
            args.run = True
        else:
            args.setup = True

    if args.setup:
        config = setup_config()
        if config and input("Start the file mover now? (y/n): ").lower() == 'y':
            run_with_config(config)
    elif args.run:
        config = load_config()
        if not config["local_dir"] or not config["remote_dir"] or not config["pushover_user_key"]:
            print("Incomplete configuration. Please run with --setup first.")
            return
        run_with_config(config)


if __name__ == '__main__':
    try:
        main()
    except Exception as global_error:
        logging.critical(f"Unhandled exception: {global_error}", exc_info=True)