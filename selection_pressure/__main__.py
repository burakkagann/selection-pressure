"""Entry point for ``python -m selection_pressure`` from the repo root."""
import sys
import os

# Add the selection_pressure package directory to sys.path so that
# main.py's plain imports (import config, import simulation, etc.) resolve
# to files within this package rather than top-level modules.
sys.path.insert(0, os.path.dirname(__file__))

from main import main

main()
