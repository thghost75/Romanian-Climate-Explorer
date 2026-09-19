"""ANM historical daily climate ingestion and local queries."""
__version__ = "0.1.0"


# Phase 3 uses a separate derived database; importing never starts processing.
from .phase3_api import ClimatologyStore
