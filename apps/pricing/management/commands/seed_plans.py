# apps/pricing/management/commands/seed_plans.py

from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.pricing.models import Plan


class Command(BaseCommand):
    help = "Idempotently ensures the default Plan rows exist with correct pricing."

    def handle(self, *args, **options):
        defaults = [
            dict(
                plan_type=Plan.FREE,
                name="Free Trial",
                campaigns_per_month=1,
                has_watermark=False,
                price_usd=Decimal("0.00"),
                price_ngn=Decimal("0.00"),
                price_kes=Decimal("0.00"),
                price_ghs=Decimal("0.00"),
            ),
            dict(
                plan_type=Plan.PAYG,
                name="Pay-as-you-go",
                has_watermark=False,
                price_usd=Decimal("1.99"),
                price_ngn=Decimal("1000.00"),
                price_kes=Decimal("84.00"),
                price_ghs=Decimal("5.90"),
            ),
            dict(
                plan_type=Plan.PRO,
                name="Pro Plan",
                has_watermark=False,
                priority_queue=True,
                premium_templates=True,
                daily_limit=10,
                price_usd=Decimal("4.99"),
                price_ngn=Decimal("4500.00"),
                price_kes=Decimal("375.00"),
                price_ghs=Decimal("26.50"),
            ),
        ]

        for data in defaults:
            plan_type = data.pop("plan_type")
            plan, created = Plan.objects.update_or_create(
                plan_type=plan_type,
                defaults=data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan: {plan}"))