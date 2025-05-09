import asyncio
import os
import signal
from datetime import datetime
from pathlib import Path
import logging
from configparser import ConfigParser
from .notification import NotificationManager
from .file_operator import FileOperator
from .directory_monitor import DirectoryMonitor

logger = logging.getLogger(__name__)


class FileMoverApp:
    def __init__(
        self,
        config: ConfigParser,
        notifier: NotificationManager = None,
        operator: FileOperator = None,
        monitor: DirectoryMonitor = None,
    ):
        self.config = config
        self.remote_dir = Path(config["FileMover"]["remote_dir"]).expanduser().resolve()
        self.dry_run = config["FileMover"].getboolean("dry_run")
        self.scan_interval = int(config["FileMover"]["scan_interval"])
        self.inactivity_threshold = int(config["FileMover"]["inactivity_threshold_minutes"]) * 60
        self.last_move_time = datetime.now()
        self.notifier = notifier or NotificationManager(config)
        self.operator = operator or FileOperator(config)
        self.monitor = monitor or DirectoryMonitor(config)
        self.total_moved = 0
        self.total_errors = 0
        self.shutdown_requested = False

        self.configured_max_workers = int(config["FileMover"].get("max_workers", "4"))
        # Get initial concurrency value from our helper.
        self.current_concurrency = self._get_initial_concurrency()
        self.semaphore = asyncio.Semaphore(self.current_concurrency)

    def _get_initial_concurrency(self):
        try:
            load_avg = os.getloadavg()[0]
            if load_avg > 1:
                return max(1, self.configured_max_workers - int(load_avg))
            return self.configured_max_workers
        except (AttributeError, OSError):
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=1)
                if cpu > 80:
                    return max(1, self.configured_max_workers - 1)
                return self.configured_max_workers
            except ImportError:
                return self.configured_max_workers

    async def _dynamic_adjustment(self):
        try:
            import psutil
        except ImportError:
            logger.info("psutil not available; dynamic adjustment disabled.")
            return
        while not self.shutdown_requested:
            cpu = psutil.cpu_percent(interval=1)
            new_limit = self.configured_max_workers
            if cpu > 80:
                new_limit = max(1, self.configured_max_workers - 1)
            elif cpu < 50:
                new_limit = self.configured_max_workers
            # Compare with our stored value instead of accessing semaphore._value.
            if new_limit != self.current_concurrency:
                logger.info(f"Adjusting concurrency: CPU usage {cpu}%, setting concurrency limit to {new_limit}")
                self.current_concurrency = new_limit
                self.semaphore = asyncio.Semaphore(new_limit)
            await asyncio.sleep(30)


    async def process_file(self, file: Path):
        dest = self.remote_dir / file.name
        async with self.semaphore:
            success = await self.operator.move_file_with_retry(file, dest)
            if success:
                logger.info(f"File {file.name} moved successfully")
                self.total_moved += 1
                self.last_move_time = datetime.now()
            else:
                logger.error(f"Failed to move file {file.name}")
                self.total_errors += 1

    async def run(self):
        logger.info("Starting FileMoverApp")
        self.remote_dir.mkdir(parents=True, exist_ok=True)
        # Send startup notification
        startup_message = (
            f"File Mover started.\nMonitoring: {self.config['FileMover']['local_dir']}\n"
            f"Destination: {self.config['FileMover']['remote_dir']}"
        )
        await self.notifier.send_notification(startup_message, title="File Mover Started")

        loop = asyncio.get_running_loop()
        for signame in {'SIGINT', 'SIGTERM'}:
            try:
                loop.add_signal_handler(getattr(signal, signame), self.request_shutdown)
            except NotImplementedError:
                logger.info(f"Signal handling for {signame} not implemented on this platform.")

        # Start dynamic adjustment as a background task.
        adjustment_task = asyncio.create_task(self._dynamic_adjustment())

        try:
            while not self.shutdown_requested:
                files = await self.monitor.scan_directory()
                if files:
                    tasks = [asyncio.create_task(self.process_file(f)) for f in files]
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    if (datetime.now() - self.last_move_time).total_seconds() > self.inactivity_threshold:
                        await self.notifier.send_notification(
                            f"No files moved in over {self.inactivity_threshold / 60:.1f} minutes.",
                            title="Inactivity Alert"
                        )
                        self.last_move_time = datetime.now()
                await asyncio.sleep(self.scan_interval)
        except Exception as e:
            logger.exception("Error in main loop: %s", e)
        finally:
            logger.info("Shutdown requested, initiating shutdown procedure...")
            adjustment_task.cancel()
            try:
                await adjustment_task
            except asyncio.CancelledError:
                logger.info("Dynamic adjustment task cancelled.")

            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if pending:
                logger.info(f"Cancelling {len(pending)} pending tasks...")
                for task in pending:
                    logger.debug(f"Cancelling task: {task}")
                    task.cancel()
                try:
                    await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for pending tasks to cancel.")

            health_message = f"FileMover stopped. Total moved: {self.total_moved}, errors: {self.total_errors}"
            await self.notifier.send_notification(health_message, title="Shutdown Notification")
            logger.info("FileMoverApp shutdown complete")

    def request_shutdown(self):
        logger.info("Shutdown requested")
        self.shutdown_requested = True
