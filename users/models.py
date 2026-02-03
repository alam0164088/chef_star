from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

class User(AbstractUser):
    AGE_CHOICES = [
        ('5-10', '5-10 yrs'),
        ('10-15', '10-15 yrs'),
        ('15-17', '15-17 yrs'),
    ]
    email = models.EmailField(unique=True)
    is_email_verified = models.BooleanField(default=False)
    
    # Parental Details
    chef_star_name = models.CharField(max_length=100, blank=True, null=True)
    age_group = models.CharField(max_length=10, choices=AGE_CHOICES, blank=True, null=True)
    parent_email = models.EmailField(null=True, blank=True)
    is_parent_approved = models.BooleanField(default=False)
    
    # ভেরিফিকেশনের জন্য ইউনিক টোকেন
    verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    # numeric code for email verification (sent to user's email)
    email_verification_code = models.CharField(max_length=6, blank=True)
    code_created_at = models.DateTimeField(null=True, blank=True)
    token_version = models.IntegerField(default=0)

    def __str__(self):
        return self.username