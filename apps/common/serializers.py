from rest_framework import serializers


class APIErrorResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    fields = serializers.DictField()


class HealthResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    status = serializers.CharField()


class CSRFTokenResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()
