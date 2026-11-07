"""CHESS ELO 5000: local rules, persisted games and bounded engine evidence."""
__version__ = "0.1.0-development"

from .api import create_app

__all__ = ["create_app", "__version__"]
