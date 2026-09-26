"""Pytest bootstrap: put the backend package root on sys.path so tests can
`import models` / `from services.x import y` exactly as the app does."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
