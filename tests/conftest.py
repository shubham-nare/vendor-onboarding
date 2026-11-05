"""Tests exercise the development tools (person switcher, demo scenarios), so they're on here."""
import os

os.environ.setdefault("DEMO_TOOLS", "true")
os.environ.setdefault("NEWS_SEARCH", "false")          # no network in tests; the reliability tests fake the sources
os.environ["OPENSANCTIONS_API_KEY"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""
