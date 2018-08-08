"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from __future__ import print_function
from __future__ import absolute_import, unicode_literals

import logging
import os
import sys
from logging import config as logging_config
import subprocess

import django
from os.path import abspath, dirname, join

DEBUG = True


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'old.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
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

DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = "test_"
