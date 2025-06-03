# File Mover with Pushover Notifications

A simple cross‑platform tool designed for labs that record neural data (e.g., using an Intan acquisition system). Because the Intan system writes a new `.rhd` file every minute, and saving directly to a remote drive can cause crashes if the network connection drops, this script watches a local folder, waits for each minute‑long file to finish writing, then moves it to a remote location. It also sends Pushover alerts so you always know if something goes wrong or if no files have been moved for a while.

---

## Table of Contents

- [File Mover with Pushover Notifications](#file-mover-with-pushover-notifications)
  - [Table of Contents](#table-of-contents)
  - [Why This Tool?](#why-this-tool)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Project Overview](#project-overview)
  - [Configuration](#configuration)
  - [How to Use](#how-to-use)
    - [Interactive Setup](#interactive-setup)
    - [Starting the File Mover](#starting-the-file-mover)
  - [What Happens Under the Hood](#what-happens-under-the-hood)
    - [Waiting for Each `.rhd` File to Finish](#waiting-for-each-rhd-file-to-finish)
    - [Moving Files Safely](#moving-files-safely)
    - [Handling Multiple Files in Parallel](#handling-multiple-files-in-parallel)
    - [Notifications](#notifications)
    - [Logging](#logging)
  - [Troubleshooting](#troubleshooting)
  - [Development Notes](#development-notes)
  - [License](#license)

---

## Why This Tool?

When recording neural data with an Intan system, each minute of acquisition gets saved as a `.rhd` file. If you try to write directly to a network drive (e.g., an NFS or SMB share) and that connection drops even briefly, the Intan software can crash, losing data. To avoid that:

1. **Save each minute’s `.rhd` file locally** (on a USB or local SSD).  
2. **Use this script** to detect when each `.rhd` file is fully written, then move it to your remote archive automatically.  
3. **Get Pushover alerts** if any file move fails, if nothing has moved in a while, or when the mover starts and stops.

That way, your Intan acquisition runs uninterrupted, and completed data files are quietly copied over whenever the network is available.

---

## Prerequisites

- A Pushover account (to obtain a user key)  
- **conda** (for creating the environment)  

---

## Installation

1. Clone this repository (replace `<repo-url>` with your URL):

   ```bash
   git clone <repo-url> file_mover
   cd file_mover
   ```

2. Create and activate a conda environment:

   ```bash
   conda create --name filemover-env python -y
   conda activate filemover-env
   ```

3. Install the required Python packages:

   ```bash
   pip install -r filemover/requirements.txt
   ```

---

## Project Overview

```
file_mover/
├── cli.py                # “python -m file_mover.cli” entry point: setup and run
├── config.py             # Reads/writes config.ini settings
├── directory_monitor.py  # Watches the local folder and checks .rhd files for stability
├── file_mover_app.py     # Main loop: moves files and sends notifications
├── file_operator.py      # Handles copying, renaming, retry logic, and locks
├── logging_setup.py      # Sets up logging to both a rotating file and the console
└── notification.py       # Sends Pushover messages
```

- All settings live in a `config.ini` file found alongside this code.  
- You run `cli.py` to configure it and then to start the mover.  
- The program writes detailed logs to `file_mover/file_mover.log` and shows key messages on your screen.

---

## Configuration

A `config.ini` file in the project folder holds all settings. If you haven’t created one yet, run the interactive setup (see next section), and it will generate a sensible `config.ini`. Here’s an example of what it looks like:

```ini
[FileMover]
local_dir = /data/intan/local        ; folder where Intan writes .rhd files
remote_dir = /mnt/network/archive    ; where completed .rhd files should end up
stability_wait = 5                   ; seconds to wait until .rhd file “settles”
scan_interval = 10                   ; seconds between checks for new stable files
inactivity_threshold_minutes = 5     ; minutes of no moves before sending a warning
pushover_app_token = agsvfrtdcnc7iqqwhps89nrgmcya5a
pushover_user_key = YOUR_USER_KEY_HERE
selected_devices = phone,tablet      ; Pushover device names to notify
dry_run = False                      ; True = simulate moves, don’t actually move files
file_filter = .rhd                    ; only move files ending in .rhd
progress_tracking_threshold_bytes = 52428800  ; not used currently
verify_checksum = False              ; True = compute SHA256 to confirm copy
health_notification_interval = 3600  ; seconds between “health check” messages
notification_rate_limit = 30         ; seconds minimum between Pushover messages
max_workers = 4                      ; how many files to move at once
```

**You can open and edit `config.ini` directly**, but it’s easier to use the wizard below.

---

## How to Use

### Interactive Setup

Run the setup wizard first (or whenever you want to change settings):

```bash
python -m file_mover.cli setup
```

- You’ll be prompted for the local folder (e.g., where Intan puts `.rhd` files) and the remote folder (your network archive).  
- You’ll set how long to wait until each file is considered “complete” (`stability_wait`) and how often to check (`scan_interval`).  
- You’ll enter your Pushover user key (and optionally a custom app token).  
- The wizard fetches your registered Pushover devices and lets you pick which ones to alert.  
- You can choose “dry run” if you want to test without actually moving files.  
- You can specify a file filter—by default it’s `.rhd` so only Intan data files are moved.  
- Finally, you pick how many files to copy at once (`max_workers`). Once finished, it writes `config.ini` and asks if you want to start immediately.

---

### Starting the File Mover

After configuring, launch the mover with:

```bash
python -m file_mover.cli run
```

- Immediately you’ll get a Pushover notification:  
  > **File Mover Started**  
  > Watching `/your/local_dir` → moving to `/your/remote_dir`
- Every `scan_interval` seconds, it looks for any `.rhd` files that haven’t changed size for `stability_wait` seconds.  
- Once a file is “stable,” the script:  
  1. Creates `filename.lock` so nothing else touches it.  
  2. Copies it to `remote_dir/filename.tmp`.  
  3. (Optional) Verifies a SHA256 checksum to confirm the copy is perfect.  
  4. Renames `filename.tmp` → `filename` in the remote folder.  
  5. Deletes the original `.rhd` file and the `.lock`.  
  6. Logs what happened and sends alerts if there’s an error.

- If no files have been moved for `inactivity_threshold_minutes`, you get an “Inactivity Warning.”  
- If any move fails (after 5 retry attempts), you get an error alert.  
- To stop the mover, press `Ctrl+C`. You’ll receive one last Pushover message summarizing how many files moved and how many errors occurred.

---

## What Happens Under the Hood

### Waiting for Each `.rhd` File to Finish

Intan writes a new `.rhd` file every minute; until it finishes, the file size might keep changing. The script:

1. Checks a file’s size.  
2. Waits 0.5 seconds and checks again.  
3. If unchanged for a total of `stability_wait` seconds, it’s considered “finished.”  

This ensures you don’t accidentally move a partially written file.

---

### Moving Files Safely

Instead of immediately renaming or deleting, the script:

1. **Locks** the file by creating `filename.lock` in the local folder.  
2. **Copies** the file to a temporary file in the remote folder (`filename.tmp`).  
3. **(Optional) Checksums** the source and temp copy; if they differ, it retries.  
4. **Renames** `filename.tmp` → `filename` (an atomic operation).  
5. **Deletes** the original `.rhd` file and the `.lock`.  

If any step fails (disk full, network drop, etc.), it waits and retries up to 5 times with increasing delays (so a brief glitch doesn’t stop everything).

---

### Handling Multiple Files in Parallel

By default, up to `max_workers` files can be copied at once. For example, if you’ve recorded several minutes in quick succession (or restarted the Intan system), multiple `.rhd` files might become “stable” at nearly the same time. With `max_workers = 4`, four files are moved in parallel. Once any slot frees up, the next stable file starts copying.

---

### Notifications

The script uses Pushover to keep you informed:

- **On Start:** “File Mover Started”—shows local and remote folders.  
- **Inactivity Warning:** If no file is moved for `inactivity_threshold_minutes`.  
- **Error Alert:** If a file fails all retries.  
- **On Stop:** “File Mover Stopped” with total moved and errors.  
- **Optional Health Check:** Every `health_notification_interval` seconds, summarizing stats.

You choose which of your devices (phones, tablets, etc.) get these alerts.

---

### Logging

- All details (file sizes, retries, errors) go into `file_mover/file_mover.log` (rotates at 5 MB).  
- Only important messages (start, stop, errors, inactivity) appear on your terminal.  
- Log lines include a timestamp, the module name, and the message.

---

## Troubleshooting

1. **“No `.rhd` files are moving”**  
   - Verify `local_dir` is correct and contains `.rhd` files.  
   - Make sure each `.rhd` file stops growing for at least `stability_wait` seconds; otherwise it won’t be moved.  
   - Inspect `file_mover/file_mover.log` for messages like “Checking file size” to see whether files are ever considered stable.

2. **“It’s hanging on a batch of files”**  
   - Look for leftover `filename.lock` files in `local_dir`. If you restarted the script mid‑copy, those locks block new moves—delete old `*.lock` files and restart.  
   - Add extra log lines in `process_file` (in `file_mover_app.py`) to confirm when each file begins and finishes copying. If it never finishes, the copy step might be stuck.

3. **“I’m not getting Pushover alerts”**  
   - Double‑check your Pushover app token and user key.  
   - Re‑run setup to fetch your devices again and confirm you selected at least one.  
   - Look for any API errors in the log file.

4. **“Too many files too quickly”**  
   - Increase `max_workers` (but be mindful of disk/network limits).  
   - Decrease `stability_wait` if you know each file settles faster than the default.

5. **“Import errors if I run directly”**  
   - Always run the script as a module from the project root folder, for example:  
     ```bash
     python -m file_mover.cli run
     ```

---

## Development Notes

- The code is organized into small modules in `file_mover/`—feel free to modify or add.  
- Logging is set up so you get full detail in the log file and only higher‑level info on screen.

---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
