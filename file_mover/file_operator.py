import asyncio
import os
import time
import hashlib
import random
from pathlib import Path
import aiofiles
import logging

logger = logging.getLogger(__name__)

class FileOperator:
    def __init__(self, config):
        self.dry_run = config["FileMover"].getboolean("dry_run")
        self.verify_checksum = config["FileMover"].getboolean("verify_checksum")
        self.max_bandwidth = int(config["FileMover"]["max_bandwidth"])  # bytes per second
        self.retry_attempts = 5
        self.backoff_factor = 2

    async def _acquire_lock(self, file_path: Path):
        """Acquire a lock by creating a sidecar '.lock' file."""
        lock_path = file_path.with_suffix(file_path.suffix + ".lock")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            return lock_path
        except FileExistsError:
            logger.info(f"Lock already exists for {file_path}")
            return None

    async def _release_lock(self, lock_path: Path):
        try:
            lock_path.unlink()
        except Exception as e:
            logger.exception(f"Failed to release lock {lock_path}: {e}")

    async def _copy_file_with_throttling(self, src: Path, dest: Path):
        """Copy file in chunks using aiofiles while enforcing maximum bandwidth."""
        chunk_size = 64 * 1024  # 64KB
        start_time = time.time()
        bytes_copied = 0
        total_size = src.stat().st_size
        async with aiofiles.open(src, 'rb') as fsrc, aiofiles.open(dest, 'wb') as fdest:
            while True:
                chunk = await fsrc.read(chunk_size)
                if not chunk:
                    break
                await fdest.write(chunk)
                bytes_copied += len(chunk)
                elapsed = time.time() - start_time
                if elapsed > 0:
                    current_rate = bytes_copied / elapsed
                    if current_rate > self.max_bandwidth:
                        sleep_time = (bytes_copied / self.max_bandwidth) - elapsed
                        await asyncio.sleep(sleep_time)

    def _compute_checksum(self, file_path: Path, algorithm: str = "sha256"):
        try:
            hash_func = hashlib.new(algorithm)
            with file_path.open('rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except Exception as e:
            logger.exception(f"Checksum computation failed for {file_path}: {e}")
            return None

    async def _move_file_transaction(self, src: Path, dest: Path) -> bool:
        """
        Transactional move:
          1. Copy to a temporary destination (with throttling).
          2. Optionally verify checksum.
          3. Rename temporary file to final destination.
          4. Remove the source file.
        """
        temp_dest = dest.with_suffix(dest.suffix + ".tmp")
        try:
            if self.dry_run:
                logger.info(f"Dry-run: simulated move of {src} to {dest}")
                return True

            await self._copy_file_with_throttling(src, temp_dest)
            if self.verify_checksum:
                src_checksum = await asyncio.to_thread(self._compute_checksum, src)
                dest_checksum = await asyncio.to_thread(self._compute_checksum, temp_dest)
                if src_checksum != dest_checksum:
                    raise Exception("Checksum verification failed")
            await asyncio.to_thread(os.rename, temp_dest, dest)
            await asyncio.to_thread(os.remove, src)
            return True
        except Exception as e:
            logger.exception(f"Transaction move failed for {src}: {e}")
            if temp_dest.exists():
                try:
                    await asyncio.to_thread(os.remove, temp_dest)
                except Exception as cleanup_e:
                    logger.exception(f"Failed to clean up temp file {temp_dest}: {cleanup_e}")
            return False

    async def move_file_with_retry(self, src: Path, dest: Path) -> bool:
        attempt = 0
        while attempt < self.retry_attempts:
            lock_path = await self._acquire_lock(src)
            if not lock_path:
                logger.info(f"Skipping {src} due to active lock")
                return False
            try:
                result = await self._move_file_transaction(src, dest)
                if result:
                    return True
            except Exception as e:
                logger.exception(f"Attempt {attempt + 1} failed for {src}: {e}")
            finally:
                await self._release_lock(lock_path)
            attempt += 1
            # Exponential backoff with jitter.
            backoff = self.backoff_factor ** attempt * random.uniform(0.8, 1.2)
            logger.info(f"Retrying {src} in {backoff:.2f} seconds (attempt {attempt})...")
            await asyncio.sleep(backoff)
        return False
