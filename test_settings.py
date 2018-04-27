"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from __future__ import absolute_import, unicode_literals

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
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
)

ROOT_URLCONF = 'django_elastic_migrations.urls'

SECRET_KEY = 'insecure-secret-key'

# parameters to pass to base Elasticsearch() instance
# https://elasticsearch-py.readthedocs.io/en/master/api.html#elasticsearch
# override in app vars
ELASTICSEARCH_PARAMS = {
    'hosts': [
        'localhost:9200'
    ],
}

DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT = 'django_elastic_migrations.utils.es_utils.DEFAULT_ES_CLIENT'
