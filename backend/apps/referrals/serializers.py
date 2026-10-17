from rest_framework import serializers


class ReferralSummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    share_url = serializers.URLField()
    share_message = serializers.CharField()
    waivers_available = serializers.IntegerField(
        help_text="Free service fees left (electricity and cable TV)"
    )
    waivers_expire_at = serializers.DateTimeField(allow_null=True)
    invited = serializers.IntegerField()
    qualified = serializers.IntegerField()
    can_redeem = serializers.BooleanField(help_text="This account can still enter someone's code")
    enabled = serializers.BooleanField()


class RedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
