from rest_framework import serializers
from .models import AIJob


class AIJobSerializer(serializers.ModelSerializer):

    class Meta:
        model = AIJob
        fields = "__all__"