
from django.apps import AppConfig
from django.db import connection
from django.db import transaction

class PricingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "apps.pricing"

    
    def _create_default_plans(self):
        from .models import Plan
        
        plans_data = [
            {
                'name': 'Free Trial',
                'plan_type': 'free',
                'price_usd': 0.00,
                'price_ngn': 0.00,
                'price_kes': 0.00,
                'price_ghs': 0.00,
                'price_zar': 0.00,
                'campaigns_per_month': 1,
                'has_watermark': False,
                'priority_queue': False,
                'premium_templates': False,
                'daily_limit': None,
                'is_active': True
            },
            {
                'name': 'Pay-as-you-go',
                'plan_type': 'payg',
                'price_usd': 1.99,
                'price_ngn': 1000.00,
                'price_kes': 150.00,
                'price_ghs': 15.00,
                'price_zar': 19.00,
                'campaigns_per_month': 1,
                'has_watermark': False,
                'priority_queue': False,
                'premium_templates': False,
                'daily_limit': None,
                'is_active': True
            },
            {
                'name': 'Pro Plan',
                'plan_type': 'pro',
                'price_usd': 5.00,
                'price_ngn': 4500.00,
                'price_kes': 750.00,
                'price_ghs': 75.00,
                'price_zar': 95.00,
                'campaigns_per_month': 999999,
                'has_watermark': False,
                'priority_queue': True,
                'premium_templates': True,
                'daily_limit': 10,
                'is_active': True
            }
        ]
        
        with transaction.atomic():
            for plan_data in plans_data:
                Plan.objects.get_or_create(
                    plan_type=plan_data['plan_type'],
                    defaults=plan_data
                )
            
            print("✓ Default plans created successfully!")