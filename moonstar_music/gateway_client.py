import asyncio
import json
import pathlib

import httpx
from pydantic import ValidationError

from moonstar_music.config import Settings
from moonstar_music.models import MusicBrief

_POLL_INTERVAL_SECONDS = 2
_MAX_POLL_ITERATIONS = 90

_PIPELINE_DIR = pathlib.Path(__file__).parent / "pipelines"


def _load_models() -> dict:
    return json.loads((_PIPELINE_DIR / "models.json").read_text())


def _load_pipeline(filename: str) -> str:
    template = (_PIPELINE_DIR / filename).read_text()
    for key, model in _load_models().items():
        template = template.replace("{{" + key + "}}", model)
    return template


_MUSIC_BRIEF_YAML = _load_pipeline("music_brief.yaml")


class GatewayClient:
    """HTTP client for the Moonstar gateway's pipeline submit+poll API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    async def run_pipeline(
        self, yaml_spec: str, initial_input: dict, transform_name: str
    ) -> tuple[str | None, float]:
        """Submit a pipeline and poll until complete. Returns (result_str, spend_usd)."""
        try:
            response = await self.client.post(
                f"{self.settings.moonstar_gateway_url}/pipelines/run",
                json={"yaml_spec": yaml_spec, "initial_input": initial_input},
                headers={"Authorization": f"Bearer {self.settings.moonstar_auth_token}"},
                timeout=10.0,
            )
            response.raise_for_status()
            session_id = response.json().get("session_id")

            for _ in range(_MAX_POLL_ITERATIONS):
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                status_resp = await self.client.get(
                    f"{self.settings.moonstar_gateway_url}/sessions/{session_id}",
                    headers={"Authorization": f"Bearer {self.settings.moonstar_auth_token}"},
                    timeout=10.0,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data.get("status") == "completed":
                    spend_usd = float(status_data.get("spend_usd") or 0.0)
                    for artifact in status_data.get("artifacts", []):
                        if artifact.get("transform_name") == transform_name:
                            raw = ((artifact.get("data") or {}).get("response") or "").strip()
                            if raw.startswith("```"):
                                raw = raw.split("```")[1]
                                if raw.startswith("json"):
                                    raw = raw[4:]
                            return raw.strip() or None, spend_usd
                    return None, spend_usd
                elif status_data.get("status") in ("failed", "rejected"):
                    print(f"[gateway_client] Pipeline {status_data['status']}: {status_data}")
                    return None, 0.0

            return None, 0.0
        except Exception as e:
            print(f"[gateway_client] Pipeline error: {e}")
            return None, 0.0

    async def get_brief(
        self, theme: str, mode: str, recent_titles: list[str]
    ) -> tuple[MusicBrief | None, float]:
        """Run the music_brief pipeline. mode is "instrumental" or "song"."""
        raw, spend_usd = await self.run_pipeline(
            _MUSIC_BRIEF_YAML,
            {"theme": theme, "mode": mode, "recent_titles": recent_titles},
            "arranger",
        )
        if raw is None:
            return None, spend_usd
        try:
            return MusicBrief.model_validate_json(raw), spend_usd
        except (ValidationError, ValueError) as e:
            print(f"[gateway_client] Failed to parse music brief: {e}")
            return None, spend_usd
