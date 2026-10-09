import yaml

# Reading  logging configuration from settings.yaml
with open("config\\settings.yaml", "r") as f:
    config = yaml.safe_load(f)
