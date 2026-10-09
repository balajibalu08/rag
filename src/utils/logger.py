from src.utils.config import config
import logging

# Logging basic Configuration
logging.basicConfig(
    filename=config["Application"]["logging"]["file"],
    level=config["Application"]["logging"]["level"],
    format=config["Application"]["logging"]["format"],
)
logger = logging.getLogger(__name__)
