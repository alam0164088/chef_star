from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'chef_star_name', 'age_group', 'parent_email')
        extra_kwargs = {
            'username': {'required': False, 'allow_blank': True},
            'email': {'required': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with that email already exists')
        return value

    def create(self, validated_data):
        # remove password_confirm before creating
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')

        # Ensure username exists; if not, derive from email
        username = validated_data.get('username')
        if not username:
            email = validated_data.get('email', '')
            username = email.split('@')[0] if '@' in email else email
            # ensure username uniqueness by appending suffix if needed
            base = username
            i = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{i}"
                i += 1
            validated_data['username'] = username

        user = User(**validated_data)
        user.set_password(password)
        # newly registered users are not parent-approved or email-verified by default
        user.is_parent_approved = False
        user.is_email_verified = False
        user.save()
        return user

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({'password_confirm': "Passwords do not match."})
        return attrs
