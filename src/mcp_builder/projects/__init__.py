"""Public project-generation services, independent of MCP transport."""
from .examples import get_example as get_example
from .templates import generate_project as generate_project
from .templates import list_templates as list_templates
from .validation import validate_project as validate_project
