from drf_spectacular.extensions import OpenApiAuthenticationExtension


class IntegrationKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.common.integration.IntegrationKeyAuthentication"
    name = "integrationKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-MedCore-Integration-Key",
        }
