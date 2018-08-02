# coding=utf-8
from __future__ import (absolute_import, division, print_function, unicode_literals)
from django.conf import settings
from elasticsearch_dsl import connections
from django.core.cache import caches
from django import db

ES_CLIENT = None


def create_es_client():
    """
    Specified this way so as to facilitate closing and recreating in multiprocessing environments;
    see below
    :return:
    """
    global ES_CLIENT
    ES_CLIENT = connections.create_connection(**settings.ELASTICSEARCH_PARAMS)


create_es_client()


########################################
# DJANGO ELASTICSEARCH MIGRATIONS CONFIGURATION ↓
########################################


def dem_close_service_connections():
    """
    Close all connections before spawning multiprocesses indexing.
    Only called during `es_update --workers` for parallel indexing.
    Connections need to manually opened and closed so that threads
    don't reuse the same connection.
    https://stackoverflow.com/questions/8242837/django-multiprocessing-and-database-connections
    """

    # close db connections, they will be recreated automatically
    db.connections.close_all()

    # close ES connection, needs to be manually recreated
    connections.connections.remove_connection("default")

    # close redis connections, will be recreated automatically
    for k in settings.CACHES.keys():
        caches[k].close()


def dem_recreate_service_connections():
    """
    Recreate all connections inside spawned multiprocessing worker.
    Django does this automatically with redis and mysql, but we need
    to recreate elasticsearch connection there.
    """
    create_es_client()
