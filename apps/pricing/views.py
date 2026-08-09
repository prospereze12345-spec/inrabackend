import logging

from django.db import transaction
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Plan, UserPlan, Transaction, UsageLog
from .serializers import (
    PlanSerializer,
    UserPlanSerializer,
    InitiatePaymentSerializer,
)
from .services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class PricingViewSet(viewsets.ViewSet):
    """
    Pricing & Subscription API

    Public:
        GET  /pricing/plans/
        POST /pricing/webhook/

    Protected:
        GET  /pricing/dashboard/
        POST /pricing/initiate_payment/
        POST /pricing/verify_payment/
        POST /pricing/check_usage/
        POST /pricing/track_generation/
    """

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[AllowAny],
    )
    def plans(self, request):
        plans = Plan.objects.filter(is_active=True)

        serializer = PlanSerializer(
            plans,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def webhook(self, request):
        try:
            payment_service = PaymentService()

            signature = request.headers.get("verif-hash")

            result = payment_service.process_webhook(
                request.body,
                signature,
            )

            return Response(result)

        except Exception as e:
            logger.exception("Webhook processing failed")

            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

   

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAuthenticated],
    )
    def dashboard(self, request):
        try:
            free_plan = Plan.objects.get(plan_type=Plan.FREE)
        except Plan.DoesNotExist:
            logger.error(
                "Dashboard requested but no '%s' Plan exists in DB. "
                "Run `python manage.py seed_plans`.",
                Plan.FREE,
            )
            return Response(
                {"error": "Pricing plans are not configured yet. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        user_plan, _ = UserPlan.objects.get_or_create(
            user=request.user,
            defaults={"plan": free_plan, "is_active": True},
        )

        serializer = UserPlanSerializer(user_plan, context={"request": request})
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def initiate_payment(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = PaymentService().initiate_payment(
                user=request.user,
                plan_type=serializer.validated_data["plan_type"],
                idempotency_key=serializer.validated_data["idempotency_key"],
            )

            return Response(
                {
                    "status": result["status"],
                    "redirect_url": result.get("redirect_url"),
                    "reference": result.get("reference"),
                    "transaction_id": str(result["transaction"].id),
                }
            )

        except Plan.DoesNotExist:
            return Response(
                {"error": "Invalid plan type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.exception("Payment initiation failed")

            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def verify_payment(self, request):
        transaction_id = request.data.get("transaction_id")
        flutterwave_transaction_id = request.data.get("flutterwave_transaction_id")

        if not transaction_id:
            return Response({"error": "transaction_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not flutterwave_transaction_id:
            return Response({"error": "flutterwave_transaction_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            transaction_obj = Transaction.objects.get(id=transaction_id, user=request.user)
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = PaymentService().verify_payment(
                transaction_id=transaction_obj.id,
                flutterwave_transaction_id=flutterwave_transaction_id,
            )
            return Response({
                "status": result["status"],
                "message": result.get("message"),
                "transaction_id": str(transaction_obj.id),
            })
        except Exception as e:
            logger.exception("Payment verification failed")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def check_usage(self, request):
        try:
            user_plan = UserPlan.objects.get(user=request.user)

        except UserPlan.DoesNotExist:
            return Response(
                {
                    "can_generate": False,
                    "message": "No active plan found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user_plan.is_active:
            return Response(
                {
                    "can_generate": False,
                    "message": "Your subscription is inactive",
                }
            )

        plan = user_plan.plan

        if plan.plan_type == "pro":
            today = timezone.now().date()

            if user_plan.last_generation_date != today:
                user_plan.daily_generation_count = 0
                user_plan.last_generation_date = today
                user_plan.save(update_fields=[
                    "daily_generation_count",
                    "last_generation_date",
                ])

            remaining = max(
                0,
                (plan.daily_limit or 10)
                - user_plan.daily_generation_count,
            )

            return Response(
                {
                    "can_generate": remaining > 0,
                    "remaining": remaining,
                }
            )

        if plan.plan_type == "free":
            remaining = max(
                0,
                plan.campaigns_per_month - user_plan.campaigns_used,
            )

            return Response(
                {
                    "can_generate": remaining > 0,
                    "remaining": remaining,
                }
            )

        if plan.plan_type == "payg":
            remaining = max(0, 1 - user_plan.campaigns_used)

            return Response(
                {
                    "can_generate": remaining > 0,
                    "remaining": remaining,
                }
            )

        return Response(
            {
                "can_generate": False,
                "remaining": 0,
            }
        )

        import logging

from django.db import transaction
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Plan, UserPlan, Transaction, UsageLog
from .serializers import (
    PlanSerializer,
    UserPlanSerializer,
    InitiatePaymentSerializer,
)
from .services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class PricingViewSet(viewsets.ViewSet):
    """
    Pricing & Subscription API
    ...
    """

    # ... plans, webhook, dashboard, initiate_payment, verify_payment,
    #     check_usage all stay exactly as they were ...

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def check_usage(self, request):
        # ...unchanged...
        return Response(
            {
                "can_generate": False,
                "remaining": 0,
            }
        )

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def track_generation(self, request):
        campaign_id = request.data.get("campaign_id")
        if not campaign_id:
            return Response(
                {"error": "campaign_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_plan = UserPlan.objects.get(user=request.user)
        except UserPlan.DoesNotExist:
            return Response(
                {"error": "No active plan found. Visit the dashboard first."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            user_plan.campaigns_used += 1
            user_plan.campaigns_generated += 1
            user_plan.daily_generation_count += 1
            user_plan.last_generation_date = timezone.now().date()
            user_plan.save()

            UsageLog.objects.create(
                user=request.user,
                campaign_id=campaign_id,
                action="generated",
                metadata={"plan": user_plan.plan.plan_type},
            )

        return Response({"success": True, "campaigns_used": user_plan.campaigns_used})