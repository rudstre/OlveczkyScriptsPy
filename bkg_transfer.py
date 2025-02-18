import os
import time
import shutil
import requests
from pushover import init, Client


def file_is_stable(filepath, wait_time):
    """
    Check if a file's size remains unchanged over wait_time seconds.
    """
    try:
        initial_size = os.path.getsize(filepath)
    except OSError:
        return False
    time.sleep(wait_time)
    try:
        later_size = os.path.getsize(filepath)
    except OSError:
        return False
    return initial_size == later_size


def move_completed_files(local_dir, remote_dir, stability_wait, client, selected_devices):
    """
    For each file in local_dir that is stable, attempt to move it to remote_dir.
    If the move fails, send a notification to each selected device.
    """
    for filename in os.listdir(local_dir):
        src_path = os.path.join(local_dir, filename)
        if os.path.isfile(src_path) and file_is_stable(src_path, stability_wait):
            dest_path = os.path.join(remote_dir, filename)
            try:
                shutil.move(src_path, dest_path)
                print(f"Moved {filename} to {remote_dir}.")
            except Exception as e:
                error_message = f"Error moving {filename}: {e}"
                print(error_message)
                notify_devices(client, selected_devices, error_message, title="File Move Error")


def get_devices(app_token, user_key):
    """
    Retrieve the list of devices using the Pushover validate endpoint.
    """
    url = "https://api.pushover.net/1/users/validate.json"
    payload = {"token": app_token, "user": user_key}
    resp = requests.post(url, data=payload)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == 1:
        return data.get("devices", [])
    return []


def notify_devices(client, devices, message, title="Notification"):
    """
    Send the specified message to each device in devices.
    """
    print(message)
    for device in devices:
        client.send_message(message, title=title, device=device)


def main():
    # --- Get directory and timing parameters ---
    local_dir = input("Enter the local directory where files are being saved: ").strip()
    remote_dir = input("Enter the remote folder to move files to: ").strip()

    try:
        stability_wait = float(input("Enter the wait time (in seconds) to check if a file is stable (e.g., 5): ").strip())
    except ValueError:
        print("Invalid wait time.")
        return

    try:
        scan_interval = float(input("Enter the scan interval (in seconds) for checking the directory (e.g., 10): ").strip())
    except ValueError:
        print("Invalid scan interval.")
        return

    if not os.path.isdir(local_dir):
        print("Error: The specified local directory does not exist.")
        return
    if not os.path.isdir(remote_dir):
        print("Error: The specified remote directory does not exist.")
        return

    # --- Pushover credentials and initialization ---
    app_token = input("Enter your Pushover App Token: ").strip()
    user_key = input("Enter your Pushover User Key: ").strip()

    init(app_token)
    client = Client(user_key)

    if not client.verify():
        print("No devices found for this account.")
        return

    devices = get_devices(app_token, user_key)
    if not devices:
        print("No devices returned from API.")
        return

    # --- Let the user select which devices to use ---
    print("\nDevices associated with your account:")
    for idx, device in enumerate(devices):
        print(f"  {idx + 1}. {device}")
    selection = input("Enter the number(s) of the device(s) to use (comma separated): ").strip()
    try:
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
        selected_devices = [devices[i] for i in indices if 0 <= i < len(devices)]
    except Exception as e:
        print("Invalid selection:", e)
        return

    if not selected_devices:
        print("No valid devices selected. Exiting.")
        return

    print("Selected devices:", ", ".join(selected_devices))
    print(f"\nMonitoring '{local_dir}' and moving files to '{remote_dir}' every {scan_interval} seconds...\n")

    disconnected = False

    # --- Main monitoring loop ---
    while True:
        # Check directory accessibility
        if not disconnected:
            if not os.path.isdir(local_dir):
                message = f"Error: Local directory ({local_dir}) is no longer accessible."
                notify_devices(client, selected_devices, message, title="Local Disconnect")
                disconnected = True
                continue
            if not os.path.isdir(remote_dir):
                message = f"Error: Remote directory ({remote_dir}) has disconnected."
                notify_devices(client, selected_devices, message, title="Remote Disconnect")
                disconnected = True
                continue

            move_completed_files(local_dir, remote_dir, stability_wait, client, selected_devices)
        else:
            # If previously disconnected, check if both directories are now accessible
            if os.path.isdir(local_dir) and os.path.isdir(remote_dir):
                message = "Good: Directories have reconnected."
                notify_devices(client, selected_devices, message, title="Reconnection")
                disconnected = False

        time.sleep(scan_interval)


if __name__ == '__main__':
    main()
