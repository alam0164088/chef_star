from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('verify-email/', views.verify_email_code, name='verify_email_code'),
    path('resend-code/', views.resend_verification_code, name='resend_verification_code'),
    path('submit-parent/', views.submit_parent, name='submit_parent'),
    path('approve-parent/<uuid:token>/', views.approve_parent, name='approve_parent'),
    path('login/', views.login_view, name='login'),
    path('profile/', views.profile, name='profile'),  # added profile route
]
