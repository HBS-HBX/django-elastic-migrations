"""
Migrate Elasticsearch-DSL Schemas in Django.
"""


import sys

from django_elastic_migrations.utils import loading
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger

__version__ = '0.8.2'

default_app_config = 'django_elastic_migrations.apps.DjangoElasticMigrationsConfig'  # pylint: disable=invalid-name

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = get_logger()

if not hasattr(settings, 'DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT'):
    raise ImproperlyConfigured(
        'The DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT setting is required. '
        'This should be the python path to the elasticsearch client '
        'to use for indexing.')


try:
    es_client = loading.import_module_element(settings.DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT)
except ImportError:
    logger.error("DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT {} not found. Please check your python path and django settings ".format(
        settings.DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT))
    raise

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


user_close_service_connections = None
user_close_service_connections_path = getattr(settings, "DJANGO_ELASTIC_MIGRATIONS_CLOSE_CONNECTIONS", "")
if user_close_service_connections_path:
    user_close_service_connections = loading.import_module_element(user_close_service_connections_path)


user_recreate_service_connections = None
user_recreate_service_connections_path = getattr(settings, "DJANGO_ELASTIC_MIGRATIONS_RECREATE_CONNECTIONS", "")
if user_recreate_service_connections_path:
    user_recreate_service_connections = loading.import_module_element(user_recreate_service_connections_path)


es_test_prefix = "test_"


if 'test' in sys.argv and not environment_prefix == es_test_prefix:
    environment_prefix = '{}{}'.format(es_test_prefix, environment_prefix)

from django_elastic_migrations import apps, indexes
__all__ = [apps, indexes]


from django_elastic_migrations.indexes import DEMIndex, DEMIndexManager
