import logging
import sys

def setup_logging(level: int = logging.INFO, log_file: str = None) -> None:
    """
    Call this ONCE at application startup (main.py / entrypoint).
    All other modules just do: logger = logging.getLogger(__name__)
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )