from pathlib import Path

import yaml

# getting project root file
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_FILE = PROJECT_ROOT / "config" / "settings.yaml"

# Reading  logging configuration from settings.yaml
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

except FileNotFoundError as exc:
    raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}") from exc

except yaml.YAMLError as exc:
    raise ValueError(f"Invalid YAML configuration: {CONFIG_FILE}") from exc


if not isinstance(config, dict):
    raise ValueError("Configuration must contain a YAML dictionary.")
