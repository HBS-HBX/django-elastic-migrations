# -*- coding: utf-8 -*-
"""
django_elastic_migrations Django application initialization.
"""

from __future__ import absolute_import, unicode_literals

import logging

from django.apps import AppConfig


class DjangoElasticMigrationsConfig(AppConfig):
    """
    Configuration for the django_elastic_migrations Django application.
    """

    name = 'django_elastic_migrations'
    index_handler = None

    def ready(self):
        log = logging.getLogger('django_elastic_migrations')
        self.stream = logging.StreamHandler()
        self.stream.setLevel(logging.INFO)
        log.addHandler(self.stream)
