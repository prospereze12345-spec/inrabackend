from django.core.management.base import BaseCommand
from apps.pricing.models import Plan


class Command(BaseCommand):
    help = "Idempotently ensures the default Plan rows exist."

    def handle(self, *args, **options):
        defaults = [
            dict(plan_type=Plan.FREE, name="Free Trial", campaigns_per_month=3, has_watermark=True),
            dict(plan_type=Plan.PAYG, name="Pay-as-you-go", has_watermark=False),
            dict(plan_type=Plan.PRO, name="Pro Plan", has_watermark=False,
                 priority_queue=True, premium_templates=True, daily_limit=10),
        ]

        for data in defaults:
            plan_type = data.pop("plan_type")
            plan, created = Plan.objects.update_or_create(
                plan_type=plan_type, defaults=data,
            )
            action = "Created" if created else "Verified"
            self.stdout.write(self.style.SUCCESS(f"{action} plan: {plan}"))