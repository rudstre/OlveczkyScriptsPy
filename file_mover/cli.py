import argparse
import asyncio
from .config import load_config, save_config
from .file_mover_app import FileMoverApp
from .logging_setup import setup_logging

def interactive_setup():
    import requests
    config = load_config()
    print("=" * 60)
    print("File Mover Configuration Setup")
    print("=" * 60)
    section = config["FileMover"]

    local_dir = input(f"Local directory [{section['local_dir']}]: ").strip()
    if local_dir:
        section["local_dir"] = local_dir
    elif not section["local_dir"]:
        print("Local directory is required")
        return None

    remote_dir = input(f"Remote directory [{section['remote_dir']}]: ").strip()
    if remote_dir:
        section["remote_dir"] = remote_dir
    elif not section["remote_dir"]:
        print("Remote directory is required")
        return None

    stability_wait = input(f"Stability wait (seconds) [{section['stability_wait']}]: ").strip()
    if stability_wait:
        section["stability_wait"] = stability_wait

    scan_interval = input(f"Scan interval (seconds) [{section['scan_interval']}]: ").strip()
    if scan_interval:
        section["scan_interval"] = scan_interval

    inactivity = input(f"Inactivity threshold (minutes) [{section['inactivity_threshold_minutes']}]: ").strip()
    if inactivity:
        section["inactivity_threshold_minutes"] = inactivity

    pushover_user_key = input(f"Pushover User Key [{section['pushover_user_key']}]: ").strip()
    if pushover_user_key:
        section["pushover_user_key"] = pushover_user_key

    pushover_app_token = input(f"Pushover App Token [{section['pushover_app_token']}]: ").strip()
    if pushover_app_token:
        section["pushover_app_token"] = pushover_app_token

    # Retrieve and prompt for device selection using Pushover's validate endpoint.
    print("\nRetrieving available devices from Pushover...")
    url = "https://api.pushover.net/1/users/validate.json"
    payload = {
        "token": section["pushover_app_token"],
        "user": section["pushover_user_key"]
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 1:
            devices = data.get("devices", [])
        else:
            print("Error retrieving devices:", data.get("errors"))
            devices = []
    except Exception as e:
        print("Error connecting to Pushover:", e)
        devices = []

    if devices:
        print("\nDevices associated with your account:")
        for idx, device in enumerate(devices):
            print(f"  {idx + 1}. {device}")
        selection = input("Enter the number(s) of the device(s) to use (comma separated, or 'all'): ").strip()
        if selection:
            if selection.lower() == 'all':
                section["selected_devices"] = ",".join(devices)
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    selected_devices = [devices[i] for i in indices if 0 <= i < len(devices)]
                    if not selected_devices:
                        print("No valid devices selected. Please try again.")
                        return None
                    section["selected_devices"] = ",".join(selected_devices)
                except Exception as selection_error:
                    print(f"Error during device selection: {selection_error}")
                    return None
        else:
            print("No device selection made. Please enter at least one device.")
            return None
    else:
        print("No devices found for your Pushover account. Please check your credentials.")
        return None

    dry_run = input(f"Enable dry-run mode? (y/n) [{section['dry_run']}]: ").strip().lower()
    section["dry_run"] = "True" if dry_run == "y" else "False"

    file_filter = input(f"File filter (extension or regex: pattern) [{section['file_filter']}]: ").strip()
    if file_filter:
        section["file_filter"] = file_filter

    verify_checksum = input(f"Enable checksum verification? (y/n) [{section['verify_checksum']}]: ").strip().lower()
    section["verify_checksum"] = "True" if verify_checksum == "y" else "False"

    max_workers = input(f"Max workers [{section['max_workers']}]: ").strip()
    if max_workers:
        section["max_workers"] = max_workers

    save_config(config)
    print("Configuration updated successfully!")
    return config

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Async File Mover with Pushover Notifications")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup_parser = subparsers.add_parser("setup", help="Run configuration setup")
    run_parser = subparsers.add_parser("run", help="Run the file mover")
    test_parser = subparsers.add_parser("test", help="Run unit tests")
    args = parser.parse_args()

    if args.command == "setup":
        config = interactive_setup()
        if config:
            start = input("Start file mover now? (y/n): ").strip().lower()
            if start == "y":
                asyncio.run(FileMoverApp(config).run())
    elif args.command == "run":
        config = load_config()
        if (not config["FileMover"]["local_dir"] or not config["FileMover"]["remote_dir"]
            or not config["FileMover"]["pushover_user_key"]):
            print("Incomplete configuration. Run setup first.")
            return
        asyncio.run(FileMoverApp(config).run())
    elif args.command == "test":
        import unittest, sys
        from .tests.test_file_operator import FileOperatorTests
        suite = unittest.TestLoader().loadTestsFromTestCase(FileOperatorTests)
        result = unittest.TextTestRunner().run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':
    main()
