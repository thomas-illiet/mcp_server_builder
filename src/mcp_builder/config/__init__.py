"""Load shared upstream references; importing configuration never uses the network."""
import json
from importlib.resources import files

SOURCE_CONFIG = json.loads(files(__package__).joinpath("sources.json").read_text(encoding="utf-8"))
MODEL_ID = SOURCE_CONFIG["model"]["id"]
MODEL_REVISION = SOURCE_CONFIG["model"]["revision"]
