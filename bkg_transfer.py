import os
import time
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def file_is_stable(filepath, stability_wait):
    """
    Check if the file's last modification time is older than the specified stability_wait time,
    indicating that the file is no longer being written to.
    """
    try:
        last_modified_time = os.path.getmtime(filepath)
    except OSError as e:
        logging.error(f"Error accessing file {filepath}: {e}")
        return False  # The file may not be accessible yet.
    
    current_time = time.time()
    return (current_time - last_modified_time) > stability_wait

def move_file_if_stable(src_path, dest_path, stability_wait):
    """
    Move the file if it is stable.
    """
    if os.path.isfile(src_path) and file_is_stable(src_path, stability_wait):
        try:
            shutil.move(src_path, dest_path)
            logging.info(f"Moved {os.path.basename(src_path)} to {dest_path}.")
        except Exception as e:
            logging.error(f"Error moving {os.path.basename(src_path)}: {e}")

def move_completed_files(local_dir, remote_dir, stability_wait):
    """
    Iterate over files in the local directory and move those that are stable
    (i.e., no changes in file size over the stability_wait time) to the remote directory.
    """
    for filename in os.listdir(local_dir):
        src_path = os.path.join(local_dir, filename)
        dest_path = os.path.join(remote_dir, filename)
        move_file_if_stable(src_path, dest_path, stability_wait)

def main():
    # Prompt the user for directories.
    local_dir = input("Enter the local directory where files are being saved: ").strip()
    remote_dir = input("Enter the remote folder to move files to: ").strip()

    # Validate that both directories exist.
    if not os.path.isdir(local_dir):
        logging.error(f"Local directory {local_dir} does not exist.")
        return
    if not os.path.isdir(remote_dir):
        logging.error(f"Remote directory {remote_dir} does not exist.")
        return

    # Prompt for stability wait time and scan interval.
    try:
        stability_wait = float(input("Enter the wait time (in seconds) to check if a file is stable (e.g., 5): ").strip())
    except ValueError:
        logging.error("Invalid wait time. Please enter a valid number.")
        return

    try:
        scan_interval = float(input("Enter the scan interval (in seconds) for checking the directory (e.g., 10): ").strip())
    except ValueError:
        logging.error("Invalid scan interval. Please enter a valid number.")
        return

    logging.info(f"Monitoring '{local_dir}' and moving completed files to '{remote_dir}' every {scan_interval} seconds...")

    # Main monitoring loop.
    while True:
        move_completed_files(local_dir, remote_dir, stability_wait)
        time.sleep(scan_interval)

if __name__ == "__main__":
    main()