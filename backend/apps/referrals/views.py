from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import services
from .serializers import RedeemSerializer, ReferralSummarySerializer


class RedeemThrottle(UserRateThrottle):
    scope = "referral"


class MyReferralView(APIView):
    """My code to share, my free fees, and how many people I've invited."""

    @extend_schema(responses=ReferralSummarySerializer)
    def get(self, request):
        return Response(ReferralSummarySerializer(services.summary(request.user)).data)


class RedeemView(APIView):
    """'I have a code': for new accounts that didn't enter one at sign-up."""

    throttle_classes = [RedeemThrottle]

    @extend_schema(request=RedeemSerializer, responses=ReferralSummarySerializer)
    def post(self, request):
        s = RedeemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.attribute(request.user, s.validated_data["code"])
        return Response(ReferralSummarySerializer(services.summary(request.user)).data)
