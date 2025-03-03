import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging():
    # Create the root logger with the lowest level
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # capture all logs

    # File handler: logs everything (DEBUG and above)
    log_file = Path(__file__).parent / "file_mover.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console (Stream) handler: logs only INFO and higher levels
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
