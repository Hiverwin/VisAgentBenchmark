"""Logging setup."""
import logging
from config.settings import Settings

def setup_logger(name: str, log_file=None, level=None):
    """Configure a named logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level or Settings.LOG_LEVEL)

    formatter = logging.Formatter(Settings.LOG_FORMAT, datefmt=Settings.LOG_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

app_logger = setup_logger("app", Settings.APP_LOG_FILE)
error_logger = setup_logger("error", Settings.ERROR_LOG_FILE, "ERROR")
