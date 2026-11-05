"""Tests exercise the development tools (person switcher, demo scenarios), so they're on here."""
import os

os.environ.setdefault("DEMO_TOOLS", "true")
os.environ.setdefault("NEWS_SEARCH", "false")          # no network in tests; the reliability tests fake the sources
os.environ.setdefault("CAPTCHA", "false")               # the bot-check tests turn it on themselves
os.environ.setdefault("RATE_LIMITS", "false")           # tests switch them on in test_security.py
os.environ["OPENSANCTIONS_API_KEY"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""                     # "Continue with Google" off unless a test turns it on
os.environ["GOOGLE_CLIENT_SECRET"] = ""
