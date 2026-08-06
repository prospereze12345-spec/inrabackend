"""
QStash calls this endpoint over HTTPS instead of a Celery worker pulling
from a broker. Add the route in urls.py (see urls_snippet.py) and make sure
QSTASH_WEBHOOK_URL in settings.py points at this exact, publicly reachable
path (e.g. https://inrabackend-docker.onrender.com/api/ai-studio/qstash/webhook/).
"""
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from qstash import Receiver

from .jobs import run_ai_job, RetryableJobError, NonRetryableJobError

logger = logging.getLogger(__name__)

_receiver = Receiver(
    current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
    next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
)


def _non_retryable_response(message: str, status: int = 489) -> HttpResponse:
    """
    489 + Upstash-NonRetryable-Error tells QStash "don't bother retrying,
    send this straight to the Dead Letter Queue." Used for bad payloads and
    permanent processing failures — retrying those just wastes attempts.
    """
    response = JsonResponse({"error": message}, status=status)
    response["Upstash-NonRetryable-Error"] = "true"
    return response


@csrf_exempt
@require_POST
def qstash_webhook(request):
    signature = request.headers.get("Upstash-Signature", "")
    body = request.body  # raw bytes — must verify BEFORE parsing as JSON

    try:
        _receiver.verify(
            body=body.decode("utf-8"),
            signature=signature,
            url=settings.QSTASH_WEBHOOK_URL,
        )
    except Exception as exc:
        logger.warning("QStash signature verification failed: %s", exc)
        # Not a delivery problem — an unsigned/forged request. Don't retry.
        return _non_retryable_response("invalid signature", status=401)

    try:
        payload = json.loads(body)
        job_id = payload["job_id"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("QStash webhook got a malformed payload: %s", exc)
        return _non_retryable_response("malformed payload")

    try:
        run_ai_job(job_id)
    except RetryableJobError as exc:
        logger.warning("Job %s hit a retryable error: %s", job_id, exc)
        # Any non-2xx here makes QStash redeliver with backoff.
        return JsonResponse({"error": str(exc)}, status=500)
    except NonRetryableJobError as exc:
        logger.error("Job %s failed permanently: %s", job_id, exc)
        return _non_retryable_response(str(exc))

    return JsonResponse({"status": "ok"})
