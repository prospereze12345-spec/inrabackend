"""
Thin wrapper around the QStash Python SDK.

Celery model:   process_ai_job.delay(job_id)   → broker → worker pulls task
QStash model:   enqueue_ai_job(job_id)         → HTTP POST → QStash → HTTP POST to our webhook

There is no persistent worker process anymore. QStash durably stores the
message and calls our webhook over HTTPS, retrying on non-2xx responses.
"""
from __future__ import annotations

import logging

from django.conf import settings
from qstash import QStash

logger = logging.getLogger(__name__)

_client: QStash | None = None


def get_qstash_client() -> QStash:
    global _client
    if _client is None:
        _client = QStash(settings.QSTASH_TOKEN)
    return _client


def enqueue_ai_job(job_id: str, *, retries: int = 3, delay: str | None = None) -> str:
    """
    Publish a job onto QStash. Returns the QStash message_id (store this on
    the job row if you want to look it up in the Upstash console / DLQ later).

    deduplication_id prevents the same job being enqueued twice within
    QStash's dedup window (useful if a view accidentally double-submits).
    """
    client = get_qstash_client()

    res = client.message.publish_json(
        url=settings.QSTASH_WEBHOOK_URL,
        body={"job_id": str(job_id)},
        retries=retries,
        delay=delay,
        deduplication_id=f"ai-job-{job_id}",
        # QStash gives up sending to a dead endpoint eventually; this tells
        # it where to report that so we can alert instead of losing the job.
        failure_callback=settings.QSTASH_FAILURE_CALLBACK_URL,
    )

    logger.info("Enqueued AI job %s on QStash → message_id=%s", job_id, res.message_id)
    return res.message_id