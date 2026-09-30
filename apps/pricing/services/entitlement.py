
"""
apps/pricing/services/entitlement.py

Central entitlement service.

This module answers one question:

    "Can this user start a generation right now?"

IMPORTANT
---------
Checking entitlement does NOT consume the entitlement.

Actual usage is recorded only after a campaign successfully completes.
That prevents failed AI/provider jobs from charging the user.

Rules
-----
Pro (live)
    Governed by the daily limit.

PAYG
    One credit is consumed only after a successful campaign.

Free
    The configured free-trial allowance is consumed only after a
    successful campaign.

PAYG while Pro is live
    PAYG credits are preserved and are not used while Pro is active.
"""

from django.utils import timezone


DEFAULT_PRO_DAILY_LIMIT = 10


def is_pro_live(user_plan, now=None):
    """
    Return True when the user's Pro subscription is currently active.

    end_date=None is retained as support for legacy Pro rows that existed
    before expiry tracking was introduced.
    """
    now = now or timezone.now()

    return (
        user_plan.plan.plan_type == "pro"
        and user_plan.is_active
        and (
            user_plan.end_date is None
            or user_plan.end_date > now
        )
    )


def _result(
    can,
    remaining,
    source,
    message=None,
):
    return {
        "can_generate": can,
        "remaining": max(0, remaining),
        "source": source,
        "message": message,
    }


def get_entitlement(user_plan, now=None):
    """
    Read-only entitlement check.

    This function MUST NOT mutate UserPlan.

    It is safe to call from:
        - CreateAIJobView
        - dashboard/check-usage endpoints
        - payment logic
        - other read-only entitlement checks
    """
    now = now or timezone.now()
    plan = user_plan.plan

    if not user_plan.is_active:
        return _result(
            False,
            0,
            None,
            "Your subscription is inactive",
        )

    # ---------------------------------------------------------
    # PRO
    # ---------------------------------------------------------
    #
    # Pro takes priority over PAYG credits.
    #
    # PAYG credits are intentionally NOT consumed while Pro is
    # live.
    if is_pro_live(user_plan, now):
        used_today = (
            user_plan.daily_generation_count
            if user_plan.last_generation_date == now.date()
            else 0
        )

        daily_limit = (
            plan.daily_limit
            or DEFAULT_PRO_DAILY_LIMIT
        )

        remaining = max(
            0,
            daily_limit - used_today,
        )

        if remaining > 0:
            return _result(
                True,
                remaining,
                "pro",
            )

        return _result(
            False,
            0,
            "pro",
            "Daily limit reached. Try again tomorrow.",
        )

    # ---------------------------------------------------------
    # PAYG
    # ---------------------------------------------------------
    #
    # PAYG is checked before the Free plan so that a user who
    # bought a PAYG credit while on Free can use that credit.
    if user_plan.payg_credits > 0:
        return _result(
            True,
            user_plan.payg_credits,
            "payg",
        )

    # ---------------------------------------------------------
    # FREE
    # ---------------------------------------------------------
    if plan.plan_type == "free":
        free_limit = plan.campaigns_per_month or 0

        remaining = max(
            0,
            free_limit - user_plan.campaigns_used,
        )

        if remaining > 0:
            return _result(
                True,
                remaining,
                "free",
            )

        return _result(
            False,
            0,
            "free",
            "Your free trial is used up. Buy a campaign or go Pro.",
        )

    # ---------------------------------------------------------
    # EXPIRED PRO
    # ---------------------------------------------------------
    if plan.plan_type == "pro":
        return _result(
            False,
            0,
            "pro",
            "Your Pro subscription has expired. Please renew.",
        )

    # ---------------------------------------------------------
    # NO ENTITLEMENT
    # ---------------------------------------------------------
    return _result(
        False,
        0,
        None,
        "No credits left. Buy a campaign or go Pro.",
    )


def consume_generation(
    user_plan,
    source=None,
    now=None,
):
    """
    Consume ONE successfully completed generation.

    This function is intentionally separate from get_entitlement().

    The caller MUST call this only after the AI campaign has successfully
    completed.

    Returns:
        {
            "can_generate": True,
            "remaining": <remaining after consumption>,
            "source": <free/payg/pro>,
            "message": None,
        }

    If there is no entitlement, nothing is changed.
    """
    now = now or timezone.now()

    entitlement = get_entitlement(
        user_plan,
        now=now,
    )

    if not entitlement["can_generate"]:
        return entitlement

    actual_source = (
        source
        if source in {"free", "payg", "pro"}
        else entitlement["source"]
    )

    # Never allow an arbitrary caller to consume a source that the
    # user does not currently have available.
    if actual_source != entitlement["source"]:
        actual_source = entitlement["source"]

    today = now.date()

    # ---------------------------------------------------------
    # PRO
    # ---------------------------------------------------------
    if actual_source == "pro":
        if user_plan.last_generation_date != today:
            user_plan.daily_generation_count = 0

        user_plan.last_generation_date = today
        user_plan.daily_generation_count += 1

        remaining = max(
            0,
            (
                user_plan.plan.daily_limit
                or DEFAULT_PRO_DAILY_LIMIT
            )
            - user_plan.daily_generation_count,
        )

        return _result(
            True,
            remaining,
            "pro",
        )

    # ---------------------------------------------------------
    # PAYG
    # ---------------------------------------------------------
    if actual_source == "payg":
        if user_plan.payg_credits <= 0:
            return _result(
                False,
                0,
                "payg",
                "No PAYG credits left.",
            )

        user_plan.payg_credits -= 1

        remaining = user_plan.payg_credits

        return _result(
            True,
            remaining,
            "payg",
        )

    # ---------------------------------------------------------
    # FREE
    # ---------------------------------------------------------
    if actual_source == "free":
        free_limit = user_plan.plan.campaigns_per_month or 0

        if user_plan.campaigns_used >= free_limit:
            return _result(
                False,
                0,
                "free",
                "Your free trial is used up. Buy a campaign or go Pro.",
            )

        user_plan.campaigns_used += 1

        remaining = max(
            0,
            free_limit - user_plan.campaigns_used,
        )

        return _result(
            True,
            remaining,
            "free",
        )

    return _result(
        False,
        0,
        None,
        "No valid generation entitlement.",
    )
