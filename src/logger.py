import logging
import os
from pathlib import Path

cwd = Path(os.getcwd())
mylogger = logging.getLogger(__name__)
mylogger.propagate = False  # don't bubble up to the root logger


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[0m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        original_msg, original_args = record.msg, record.args
        record.msg = f"{color}{record.getMessage()}{self.RESET}"
        record.args = ()
        try:
            return super().format(record)
        finally:
            record.msg, record.args = original_msg, original_args


# log_format = (
#    "%(asctime)s %(levelname)s %(filename)-8.8s "
#    "%(funcName)s: %(lineno)-4.4d %(message)s"
# )

# log_format = "%(funcName)s %(lineno)-4.4d : %(message)s"

log_format = "%(message)s"

date_format = "%H:%M:%S"

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter(log_format, datefmt=date_format))

file_handler = logging.FileHandler(f"{cwd}/myapp.log")
file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

mylogger.setLevel(logging.DEBUG)
mylogger.handlers.clear()  # avoid stacking handlers on re-import/rerun
mylogger.addHandler(console_handler)
mylogger.addHandler(file_handler)
