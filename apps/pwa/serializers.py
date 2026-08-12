from rest_framework import serializers


class TrackEventSerializer(serializers.Serializer):
    event = serializers.ChoiceField(
        choices=[
            "prompt_shown",
            "prompt_accepted",
            "prompt_dismissed",
            "install",
            "session",
            "ios_instructions_shown",
        ]
    )
    device_id = serializers.CharField(max_length=64)
    os = serializers.CharField(max_length=32)
    browser = serializers.CharField(max_length=32)
    device_type = serializers.ChoiceField(choices=["mobile", "tablet", "desktop"])
    is_pwa = serializers.BooleanField(default=False)
    user_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    meta = serializers.JSONField(required=False, allow_null=True)
