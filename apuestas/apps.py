from django.apps import AppConfig


class ApuestasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apuestas"

    def ready(self):
        import apuestas.signals  # noqa: F401