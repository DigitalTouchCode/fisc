from django.http import HttpResponse
from django.urls import include, path

from fiscguy.models import Device


def login(request):
    return HttpResponse("login")


def only_mine(request):
    return Device.objects.filter(org_name="Mine")


urlpatterns = [
    path("login/", login, name="login"),
    path("ui/", include("fiscguy.web.urls")),
    path("", include("fiscguy.urls")),
]
