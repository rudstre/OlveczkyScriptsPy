import asyncio
import re
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DirectoryMonitor:
    def __init__(self, config):
        self.local_dir = Path(config["FileMover"]["local_dir"]).expanduser().resolve()
        self.stability_wait = int(config["FileMover"]["stability_wait"])
        self.file_filter = config["FileMover"]["file_filter"]

    async def is_file_stable(self, file: Path) -> bool:
        try:
            initial_size = file.stat().st_size
            if initial_size == 0:
                return False
            elapsed = 0.0
            poll_interval = 0.5
            while elapsed < self.stability_wait:
                await asyncio.sleep(poll_interval)
                new_size = file.stat().st_size
                if new_size != initial_size:
                    return False
                elapsed += poll_interval
            return True
        except Exception as e:
            logger.exception(f"Error checking stability for {file}: {e}")
            return False

    async def scan_directory(self):
        try:
            files = [f for f in self.local_dir.iterdir() if f.is_file()]
            if self.file_filter:
                if self.file_filter.startswith("regex:"):
                    pattern = self.file_filter[len("regex:"):].strip()
                    regex = re.compile(pattern)
                    files = [f for f in files if regex.search(f.name)]
                else:
                    files = [f for f in files if f.name.endswith(self.file_filter)]
            files.sort(key=lambda f: f.stat().st_ctime)

            # Launch all stability checks concurrently.
            stability_tasks = [self.is_file_stable(file) for file in files]
            results = await asyncio.gather(*stability_tasks, return_exceptions=True)

            stable_files = [file for file, stable in zip(files, results) if stable is True]
            logger.info(f"Scan complete: {len(stable_files)} stable files out of {len(files)}")
            return stable_files
        except Exception as e:
            logger.exception(f"Error scanning directory {self.local_dir}: {e}")
            return []
