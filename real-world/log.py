"""Minimal stdout logger with numeric log levels.

The real-world pipeline uses this tiny module instead of Python's standard
logging setup to keep output behavior consistent across local and remote runs.
"""

ERROR = 1
WARNING = 2
INFO = 3
DEBUG = 4

log_level = INFO


def set_level(level):
    """Set global log verbosity."""
    global log_level
    log_level = level


def debug(message):
    """Print debug-level message if enabled."""
    if log_level >= DEBUG:
        print(message, flush=True)


def info(message):
    """Print info-level message if enabled."""
    if log_level >= INFO:
        print(message, flush=True)


def warning(message):
    """Print warning-level message if enabled."""
    if log_level >= WARNING:
        print(message, flush=True)


def error(message):
    """Print error-level message if enabled."""
    if log_level >= ERROR:
        print(message, flush=True)
