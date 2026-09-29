"""
apps/pricing/services/entitlement.py

One place that answers "may this user generate right now?" and applies the
usage. Used by check_usage (read-only) and track_generation (consumes), and
by PaymentService when deciding whether a PAYG purchase may change the plan.

Rules
-----
Pro (live)  : governed only by the daily limit (plan.daily_limit or 10).
              PAYG credits are never spent while Pro is live.
Otherwise   : 1 PAYG credit per generation (credits persist until used).
Free plan   : falls back to the free-trial allowance when no credits exist.
"""
from django.utils import timezone

DEFAULT_PRO_DAILY_LIMIT = 10


def is_pro_live(user_plan, now=None):
    """Active Pro whose period has not ended.

    end_date is None only on legacy rows created before expiry tracking;
    those are treated as live until they are backfilled or renew.
    """
    now = now or timezone.now()
    return (
        user_plan.plan.plan_type == "pro"
        and user_plan.is_active
        and (user_plan.end_date is None or user_plan.end_date > now)
    )


def _result(can, remaining, source, message=None):
    return {
        "can_generate": can,
        "remaining": remaining,
        "source": source,
        "message": message,
    }


def get_entitlement(user_plan, now=None):
    now = now or timezone.now()
    plan = user_plan.plan

    if not user_plan.is_active:
        return _result(False, 0, None, "Your subscription is inactive")

    if is_pro_live(user_plan, now):
        used = (
            user_plan.daily_generation_count
            if user_plan.last_generation_date == now.date()
            else 0
        )
        remaining = max(0, (plan.daily_limit or DEFAULT_PRO_DAILY_LIMIT) - used)
        if remaining > 0:
            return _result(True, remaining, "pro")
        return _result(False, 0, "pro", "Daily limit reached. Try again tomorrow.")

    if user_plan.payg_credits > 0:
        return _result(True, user_plan.payg_credits, "payg")

    if plan.plan_type == "free":
        remaining = max(0, plan.campaigns_per_month - user_plan.campaigns_used)
        if remaining > 0:
            return _result(True, remaining, "free")
        return _result(False, 0, "free", "Your free trial is used up. Buy a campaign or go Pro.")

    if plan.plan_type == "pro":
        return _result(False, 0, None, "Your Pro subscription has expired. Please renew.")

    return _result(False, 0, None, "No credits left. Buy a campaign or go Pro.")


def consume_generation(user_plan, now=None):
    """Apply one generation to `user_plan` (caller saves it, inside a row lock).

    Returns the entitlement that was evaluated *before* consuming. If
    can_generate is False nothing is changed.
    """
    now = now or timezone.now()
    ent = get_entitlement(user_plan, now)
    if not ent["can_generate"]:
        return ent

    today = now.date()
    if user_plan.last_generation_date != today:
        user_plan.daily_generation_count = 0
    user_plan.last_generation_date = today
    user_plan.daily_generation_count += 1
    user_plan.campaigns_used += 1
    user_plan.campaigns_generated += 1
    if ent["source"] == "payg":
        user_plan.payg_credits -= 1
    return ent