from django.conf import settings
from elasticsearch_dsl import connections

DEFAULT_ES_CLIENT = connections.create_connection(**settings.ELASTICSEARCH_PARAMS)