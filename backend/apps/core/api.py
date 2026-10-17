"""Small public API endpoints that belong to no single app."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class MarketCountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    calling_code = serializers.CharField()
    emergency = serializers.CharField(help_text="The emergency number the apps show")
    bills = serializers.BooleanField(help_text="Airtime, data, TV and electricity available")


class MarketCitySerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    state = serializers.CharField()
    country = serializers.CharField()
    areas = serializers.ListField(child=serializers.CharField())
    discos = serializers.ListField(
        child=serializers.CharField(), help_text="Electricity companies (bills codes)"
    )


class MarketsSerializer(serializers.Serializer):
    countries = MarketCountrySerializer(many=True)
    cities = MarketCitySerializer(many=True)


class MarketsView(APIView):
    """GET /markets/: countries and cities Homesika is switched on in, with suggested areas (public)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses=MarketsSerializer)
    def get(self, request):
        from . import markets

        return Response(
            {
                "countries": [
                    {
                        "code": c.code,
                        "name": c.name,
                        "currency": c.currency,
                        "calling_code": f"+{c.calling_code}",
                        "emergency": c.emergency,
                        "bills": c.bills,
                    }
                    for c in markets.enabled_countries()
                ],
                "cities": [
                    {
                        "slug": c.slug,
                        "name": c.name,
                        "state": c.state,
                        "country": c.country,
                        "areas": list(c.areas),
                        "discos": list(c.discos),
                    }
                    for c in markets.enabled_cities()
                ],
            }
        )
