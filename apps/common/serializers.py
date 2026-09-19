from rest_framework import serializers


class HealthResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    status = serializers.CharField()


class CSRFTokenResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()
