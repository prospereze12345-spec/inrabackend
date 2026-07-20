from django.contrib import admin
from .models import Plan, UserPlan, Transaction, UsageLog

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_type', 'price_usd', 'campaigns_per_month', 'is_active']
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name']

@admin.register(UserPlan)
class UserPlanAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'is_active', 'campaigns_used', 'campaigns_generated']
    list_filter = ['is_active', 'plan']
    search_fields = ['user__email', 'user__username']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'plan', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'currency']
    search_fields = ['user__email', 'flutterwave_ref', 'idempotency_key']
    readonly_fields = ['id', 'created_at', 'updated_at']

@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'campaign_id', 'created_at']
    list_filter = ['action']
    search_fields = ['user__email', 'campaign_id']