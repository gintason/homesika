from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushDevice


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.RegexField(r"^Expo(nent)?PushToken\[[^\]]{10,180}\]$", max_length=200)
    platform = serializers.ChoiceField(choices=PushDevice.Platform.choices)


class PushDeviceView(APIView):
    """The app registers its Expo push token after sign-in, and removes it on sign-out."""

    @extend_schema(request=PushDeviceSerializer, responses={204: None})
    def post(self, request):
        s = PushDeviceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        # A token belongs to one phone: if someone else signs in on it, it moves to them.
        PushDevice.objects.update_or_create(
            token=s.validated_data["token"],
            defaults={"user": request.user, "platform": s.validated_data["platform"], "is_active": True},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=PushDeviceSerializer, responses={204: None})
    def delete(self, request):
        token = str(request.data.get("token", ""))
        PushDevice.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
