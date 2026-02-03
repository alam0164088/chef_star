from django.urls import path, include
from django.http import HttpResponse


def health(request):
    return HttpResponse('OK')

urlpatterns = [
    path('', health, name='health'),
    path('users/', include('users.urls')),
    # posts and followers can be added similarly
]
