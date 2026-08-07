# campaign/renderer_dispatch.py
import logging
from typing import Any, Dict

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GithubDispatchError(RuntimeError):
    pass


def trigger_github_render(job_id: str, config: Dict[str, Any]) -> None:
    """
    Fires a repository_dispatch event that kicks off .github/workflows/render-video.yml
    on the repo holding remotion/render.mjs. Does not wait for the render —
    the workflow calls back to video_render_complete() when it's done.
    """
    url = f"https://api.github.com/repos/{settings.GITHUB_RENDER_REPO}/dispatches"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.GITHUB_PAT}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "event_type": "render_video",
            "client_payload": {
                "job_id": str(job_id),
                "config": config,
            },
        },
        timeout=15,
    )

    if resp.status_code != 204:
        logger.error(
            "GitHub dispatch failed for job %s: %s %s",
            job_id, resp.status_code, resp.text,
        )
        raise GithubDispatchError(
            f"GitHub dispatch returned {resp.status_code}: {resp.text}"
        )

    logger.info("Dispatched render for job %s to GitHub Actions", job_id)