"""
Migrate Elasticsearch-DSL Schemas in Django.
"""

from __future__ import absolute_import, unicode_literals

import sys

from django_elastic_migrations.utils import loading
from django_elastic_migrations.utils.log import get_logger

__version__ = '0.1.3'

default_app_config = 'django_elastic_migrations.apps.DjangoElasticMigrationsConfig'  # pylint: disable=invalid-name

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = get_logger()

if not hasattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT'):
    raise ImproperlyConfigured(
        'The DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT setting is required. '
        'This should be the python path to the elasticsearch client '
        'to use for indexing.')


es_client = loading.import_module_element(settings.DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT)


codebase_id = getattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_GET_CODEBASE_ID', "")

environment_prefix = getattr(
    settings, 'DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX', "")

dem_index_paths = getattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_INDEXES', [])
if not dem_index_paths:
    logger.warning(
        "No indexes are specified in settings. To set: "
        "DJANGO_ELASTIC_MIGRATIONS_INDEXES = [ "
        " 'path.to.module.with.MyDEMSearchIndex' "
        "]"
    )

es_test_prefix = "test_"


if 'test' in sys.argv:
    environment_prefix = '{}{}'.format(es_test_prefix, environment_prefix)

from django_elastic_migrations import apps, indexes
__all__ = [apps, indexes]


from django_elastic_migrations.indexes import DEMIndex, DEMIndexManager
