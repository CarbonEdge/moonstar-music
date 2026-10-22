"""Test configuration: ensure a clean env for every test."""
import os

for _k in ("MOONSTAR_GATEWAY_URL", "MOONSTAR_AUTH_TOKEN", "ELEVENLABS_API_KEY"):
    os.environ.pop(_k, None)
