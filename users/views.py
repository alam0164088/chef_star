from django.shortcuts import get_object_or_404
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth import get_user_model

import logging
import random
import uuid
from urllib.parse import quote
from datetime import timedelta
from django.urls import reverse

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegistrationSerializer

User = get_user_model()

logger = logging.getLogger(__name__)

def _generate_code():
    return f"{random.randint(0, 999999):06d}"


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Register user and send numeric verification code to email."""
    serializer = RegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()  # serializer should create user with is_email_verified=False
        # generate and store code
        code = _generate_code()
        user.email_verification_code = code
        user.code_created_at = timezone.now()
        user.save()

        # send code email (plain + html)
        subject = "Your verification code"
        text = f"Hello {user.username},\n\nYour verification code is: {code}\n\nIt expires in 15 minutes."
        html = f"<p>Hello <strong>{user.username}</strong>,</p><p>Your verification code is: <strong>{code}</strong></p><p>It expires in 15 minutes.</p>"

        msg = EmailMultiAlternatives(subject, text, getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost'), [user.email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)

        print(f"[OTP] Sending verification code for {user.email}: {code}")

        return Response({
            "id": user.id,
            "username": user.username,
            "message": "successfully sent a verification mail"
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email_code(request):
    """
    POST { "email": "...", "code": "123456" }
    On success: mark verified and return id, username, email, token (DRF) and access/refresh (JWT if available).
    """
    email = request.data.get('email')
    code = request.data.get('code')
    if not email or not code:
        return Response({'error': 'email and code are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'user not found'}, status=status.HTTP_404_NOT_FOUND)

    # If already verified -> still return tokens so client can continue
    if user.is_email_verified:
        resp = {'id': user.id, 'username': user.username, 'email': user.email}
        try:
            token_obj, _ = Token.objects.get_or_create(user=user)
            resp['token'] = token_obj.key
        except Exception:
            pass
        try:
            refresh = RefreshToken.for_user(user)
            refresh['token_version'] = getattr(user, 'token_version', 0)
            resp['access'] = str(refresh.access_token)
            resp['refresh'] = str(refresh)
        except Exception:
            pass
        return Response(resp, status=status.HTTP_200_OK)

    # verify code + expiry
    if user.email_verification_code != code:
        return Response({'error': 'invalid code'}, status=status.HTTP_400_BAD_REQUEST)
    if not user.code_created_at or timezone.now() > user.code_created_at + timedelta(minutes=15):
        return Response({'error': 'code expired'}, status=status.HTTP_400_BAD_REQUEST)

    # mark verified
    user.is_email_verified = True
    user.email_verification_code = ''
    user.code_created_at = None
    user.save()

    # create tokens
    resp = {'id': user.id, 'username': user.username, 'email': user.email}
    try:
        token_obj, _ = Token.objects.get_or_create(user=user)
        resp['token'] = token_obj.key
    except Exception:
        pass
    try:
        refresh = RefreshToken.for_user(user)
        refresh['token_version'] = getattr(user, 'token_version', 0)
        resp['access'] = str(refresh.access_token)
        resp['refresh'] = str(refresh)
    except Exception:
        pass

    return Response(resp, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_code(request):
    """Resend verification code to a user's email. POST {email} -> sends new code."""
    email = request.data.get('email')
    if not email:
        return Response({'error': 'email required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'user not found'}, status=status.HTTP_404_NOT_FOUND)

    # If already verified, inform the client and do not resend
    if user.is_email_verified:
        return Response({'message': 'your mail already verified'}, status=status.HTTP_200_OK)

    # generate new code -> increment token_version to invalidate old JWTs
    code = _generate_code()
    user.email_verification_code = code
    user.code_created_at = timezone.now()
    user.token_version = (user.token_version or 0) + 1
    user.save()

    # send code by email (console backend in dev)
    subject = "Your verification code"
    text = f"Hello {user.username}, your verification code: {code}"
    msg = EmailMultiAlternatives(subject, text, getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost'), [user.email])
    msg.attach_alternative(f"<p>Your verification code: <strong>{code}</strong></p>", "text/html")
    msg.send(fail_silently=False)

    print(f"[OTP] Resending verification code for {user.email}: {code}")

    return Response({
        "id": user.id,
        "username": user.username,
        "subject": "verification code resent"
    }, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_parent(request):
    """
    Child posts parent_email, optional star_name/age_group.
    Sends approval email (logs and returns preview). Raises/send errors visible.
    """
    parent_email = request.data.get('parent_email')
    chef_star_name = request.data.get('star_name') or request.data.get('chef_star_name')
    age_group_raw = request.data.get('age_group')

    if not parent_email:
        return Response({'error': 'parent_email required'}, status=status.HTTP_400_BAD_REQUEST)

    # normalize age_group to model key
    age_key = None
    if age_group_raw:
        ag = str(age_group_raw).strip().lower()
        mapping = {
            '5-10': '5-10', '5-10 yrs': '5-10', '5-10 years': '5-10',
            '10-15': '10-15', '10-15 yrs': '10-15', '10-15 years': '10-15',
            '15-17': '15-17', '15-17 yrs': '15-17', '15-17 years': '15-17',
        }
        age_key = mapping.get(ag)
        if not age_key:
            cleaned = ''.join(ch for ch in ag if ch.isdigit() or ch == '-')
            if cleaned in dict(get_user_model().AGE_CHOICES):
                age_key = cleaned

    user = request.user
    user.parent_email = parent_email
    if chef_star_name:
        user.chef_star_name = chef_star_name
    if age_key:
        user.age_group = age_key
    if not getattr(user, 'verification_token', None):
        user.verification_token = uuid.uuid4()
    user.save()

    # build approve link
    token = user.verification_token
    approve_link = f"{request.scheme}://{request.get_host()}{reverse('approve_parent', args=[token])}?email={quote(parent_email)}"

    subject = f"Please approve {user.username}'s account"
    text = f"Please approve your child's account by visiting: {approve_link}"
    html = f"""
      <html>
        <body>
          <p>Hello,</p>
          <p>Please approve <strong>{user.username}</strong>'s account by clicking the button below:</p>
          <p style="text-align:center;">
            <a href="{approve_link}" style="padding:12px 20px;background:#6f42c1;color:#fff;border-radius:6px;text-decoration:none;">Approve account</a>
          </p>
        </body>
      </html>
    """

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost')

    # Try to send and capture exceptions
    try:
        msg = EmailMultiAlternatives(subject, text, from_email, [parent_email])
        msg.attach_alternative(html, "text/html")
        # ensure exceptions bubble up for debugging (fail_silently=False)
        send_result = msg.send(fail_silently=False)
        logger.info("Parent approval email sent to %s (send returned: %s)", parent_email, send_result)
        send_status = 'sent'
    except Exception as exc:
        logger.exception("Failed to send parent approval email to %s: %s", parent_email, exc)
        send_status = 'error'
        # include error in response for debugging (remove in production)
        return Response({'error': 'failed to send email', 'details': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # return saved fields + preview so you can verify what was sent
    return Response({
        'id': user.id,
        'username': user.username,
        'chef_star_name': user.chef_star_name,
        'age_group': user.age_group,
        'parent_email': user.parent_email,
        'email_preview': {
            'to': [parent_email],
            'from': from_email,
            'subject': subject,
            'text': text,
            'html': html,
        },
        'send_status': send_status
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def approve_parent(request, token):
    """
    Parent clicks link (browser): /users/approve-parent/<token>/?email=parent@example.com
    Marks is_parent_approved=True and notifies the child by email.
    Returns an HTML confirmation page.
    """
    user = get_object_or_404(User, verification_token=token)

    parent_email = request.GET.get('email')
    if parent_email and parent_email != user.parent_email:
        return HttpResponse("<h2>Parent email mismatch</h2>", status=400)

    if user.is_parent_approved:
        return HttpResponse("<h2>Already approved</h2><p>This account is already approved by the parent.</p>")

    user.is_parent_approved = True
    user.save()

    # notify the child
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost')
    send_mail(
        'Your parent approved your account',
        f'Hi {user.username},\n\nYour parent has approved your account. You can now log in.',
        from_email,
        [user.email],
        fail_silently=False,
    )

    return HttpResponse("<h2>Thank you</h2><p>Parent approval recorded. The account is now unlocked and the child can log in.</p>")

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    POST { "email": "...", "password": "..." }
    Returns: id, username, email, token (DRF Token) and access/refresh (JWT) when available.
    """
    email = request.data.get('email')
    password = request.data.get('password')
    if not email or not password:
        return Response({'error': 'email and password required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    if not getattr(user, 'is_email_verified', False):
        return Response({'error': 'email not verified'}, status=status.HTTP_403_FORBIDDEN)

    # if age_group requires parental approval, block until approved
    if getattr(user, 'age_group', None) in (choice[0] for choice in User.AGE_CHOICES) and not getattr(user, 'is_parent_approved', False):
        return Response({'error': 'parent approval required'}, status=status.HTTP_403_FORBIDDEN)

    resp = {'id': user.id, 'username': user.username, 'email': user.email}

    # DRF Token (if authtoken installed)
    try:
        token_obj, _ = Token.objects.get_or_create(user=user)
        resp['token'] = token_obj.key
    except Exception:
        pass

    # JWT (if simplejwt installed)
    try:
        refresh = RefreshToken.for_user(user)
        refresh['token_version'] = getattr(user, 'token_version', 0)
        resp['access'] = str(refresh.access_token)
        resp['refresh'] = str(refresh)
    except Exception:
        pass

    return Response(resp, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    Return authenticated user's profile.
    GET /users/profile/
    """
    user = request.user
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "chef_star_name": getattr(user, "chef_star_name", None),
        "age_group": getattr(user, "age_group", None),
        "parent_email": getattr(user, "parent_email", None),
        "is_email_verified": getattr(user, "is_email_verified", False),
        "is_parent_approved": getattr(user, "is_parent_approved", False),
    }
    return Response(data, status=status.HTTP_200_OK)