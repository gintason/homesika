from django.urls import path

from . import views

me_urls = [path("push-devices/", views.PushDeviceView.as_view(), name="push-devices")]
