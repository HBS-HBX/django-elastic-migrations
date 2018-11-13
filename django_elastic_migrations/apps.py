# -*- coding: utf-8 -*-

"""
django_elastic_migrations Django application initialization.
"""

from django.apps import AppConfig


class DjangoElasticMigrationsConfig(AppConfig):
    """
    Configuration for the django_elastic_migrations Django application.
    """

    name = 'django_elastic_migrations'
    index_handler = None

    def ready(self):
        # avoid race condition with django app initialization
        from django_elastic_migrations.indexes import DEMIndexManager
        DEMIndexManager.initialize(create_versions=True, activate_versions=True)
