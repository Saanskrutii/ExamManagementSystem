from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    name = 'authentication'

    def ready(self):
        """
        Called once when Django finishes startup.
        Ensures all compound PyMongo indexes are created in MongoDB
        before the first request is processed.
        """
        try:
            from config.db import ensure_db_indexes
            ensure_db_indexes()
        except Exception:
            # Silently skip during migrations or test runs where DB may not be ready
            pass
