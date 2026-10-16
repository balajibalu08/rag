import logging

from src.core.config import PROJECT_ROOT, config

log_file = PROJECT_ROOT / config["Application"]["logging"]["file"]
log_file.parent.mkdir(parents=True, exist_ok=True)

# Logging basic Configuration
logging.basicConfig(
    filename=log_file,
    level=config["Application"]["logging"]["level"],
    format=config["Application"]["logging"]["format"],
    datefmt=config["Application"]["logging"]["datefmt"],
)
logger = logging.getLogger("RagApp")
