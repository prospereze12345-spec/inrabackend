import logging
from typing import Any, Dict

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GithubDispatchError(RuntimeError):
    pass


def trigger_github_render(job_id: str, config: Dict[str, Any]) -> None:
    """
    Fires a repository_dispatch event that kicks off
    .github/workflows/render-video.yml.
    """

    repo = settings.GITHUB_RENDER_REPO

    url = f"https://api.github.com/repos/{repo}/dispatches"

    logger.info(
        "GitHub render dispatch → repo=%s job_id=%s",
        repo,
        job_id,
    )

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

    logger.info(
        "GitHub dispatch response → status=%s",
        resp.status_code,
    )

    if resp.status_code != 204:
        logger.error(
            "GitHub dispatch failed for job %s: %s %s",
            job_id,
            resp.status_code,
            resp.text,
        )

        raise GithubDispatchError(
            f"GitHub dispatch returned {resp.status_code}: {resp.text}"
        )

    logger.info(
        "Dispatched render for job %s to GitHub Actions",
        job_id,
    )