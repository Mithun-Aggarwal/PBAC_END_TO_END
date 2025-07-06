# logger.py

"""
Robust logging setup: initializes a logger that writes to both console and file,
with timestamps and structured output. Supports use across all pipeline modules.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(log_file_path: str = "./logs/pipeline.log") -> logging.Logger:
    """
    Set up a shared logger for the pipeline.

    Args:
        log_file_path (str): Path to the log file.

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger("document_pipeline")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers in re-execution scenarios
    if logger.hasHandlers():
        return logger

    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # File handler
    file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
