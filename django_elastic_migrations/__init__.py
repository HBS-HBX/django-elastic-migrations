"""
Migrate Elasticsearch-DSL Schemas in Django.
"""

from __future__ import absolute_import, unicode_literals

from django_elastic_migrations.utils import loading

__version__ = '0.1.3'

default_app_config = 'django_elastic_migrations.apps.DjangoElasticMigrationsConfig'  # pylint: disable=invalid-name

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


if not hasattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT'):
    raise ImproperlyConfigured(
        'The DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT setting is required. '
        'This should be the python path to the elasticsearch client '
        'to use for indexing.')


es_client = loading.import_module_element(settings.DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT)


codebase_id = getattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_GET_CODEBASE_ID', "")


from django_elastic_migrations import apps, indexes
__all__ = [apps, indexes]


from django_elastic_migrations.indexes import DEMIndex, DEMIndexManager
