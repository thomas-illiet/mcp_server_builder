"""Load shared upstream references; importing configuration never uses the network."""
import json
from importlib.resources import files

SOURCE_CONFIG = json.loads(files(__package__).joinpath("sources.json").read_text(encoding="utf-8"))
DEFAULT_EMBEDDING_MODEL = "bge-m3"
