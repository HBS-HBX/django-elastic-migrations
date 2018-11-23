from __future__ import (absolute_import, division, print_function, unicode_literals)
"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

import logging
import os
import subprocess
import sys
from logging import config as logging_config

import django
from os.path import abspath, dirname, join

DEBUG = True


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


if DEBUG:
   ALLOWED_HOSTS = ['*']


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': 5432
    },
}

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django_elastic_migrations',
    'tests'
)

ROOT_URLCONF = 'django_elastic_migrations.urls'

SECRET_KEY = 'insecure-secret-key'

# parameters to pass to base Elasticsearch() instance
# https://elasticsearch-py.readthedocs.io/en/master/api.html#elasticsearch
ELASTICSEARCH_PARAMS = {
    'hosts': [
        'localhost:9200'
    ],
}

ELASTICSEARCH_INDEX_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0
}

LOGGING = {
    "version": 1,
    "formatters": {
        "message": {
            "format": "%(levelname)s %(asctime)s %(module)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "handlers": [
                "console"
            ],
            "level": "INFO",
            "propagate": True
        },
        "django_elastic_migrations": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False
        },
        "elasticsearch": {
            "handlers": ["console"],
            "level": "WARNING",
            # locally when debugging tests, this may help:
            # "level": "DEBUG",
            "propagate": False
        },
        "elasticsearch_dsl": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        }
    },
}
logging_config.dictConfig(LOGGING)

# logger = logging.getLogger(__name__)
# logger.debug("using cwd {}".format(root()))
# logger.debug("using python path: {}".format(sys.path))

DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT = "tests.es_config.ES_CLIENT"
DJANGO_ELASTIC_MIGRATIONS_RECREATE_CONNECTIONS = "tests.es_config.dem_recreate_service_connections"
DJANGO_ELASTIC_MIGRATIONS_CLOSE_CONNECTIONS = "tests.es_config.dem_close_service_connections"
DJANGO_ELASTIC_MIGRATIONS_INDEXES = [
    "tests.search.MovieSearchIndex",
]

# DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = "test_"
