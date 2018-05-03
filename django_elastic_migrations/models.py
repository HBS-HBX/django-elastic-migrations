# -*- coding: utf-8 -*-
"""
Database models for django_elastic_migrations.
"""

from __future__ import absolute_import, unicode_literals

import datetime
import hashlib
import json

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from elasticsearch_dsl import Index as ES_DSL_Index

from django_elastic_migrations import codebase_id, es_client
from django_elastic_migrations.utils.es_utils import get_index_hash_and_json


@python_2_unicode_compatible
class Index(models.Model):
    """
    Model that retains information about all Elasticsearch indexes
    managed by django_elastic_migrations
    """
    name = models.CharField(verbose_name="Index Name", max_length=32, unique=True)
    active_version = models.ForeignKey(
        'django_elastic_migrations.IndexVersion',
        # Django convention is to use '+' for related name when you don't need the
        # reverse relation. in this case, we already have IndexVersion pointing
        # back to Index, so we don't need that reverse name.
        # See https://docs.djangoproject.com/en/2.0/ref/models/fields/#django.db.models.ForeignKey.related_name
        related_name="+", null=True)

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<Index, ID: {}>'.format(self.id)

    def get_latest_version(self):
        """
        Get the versions"
        :return:
        """
        return self.indexversion_set.last()

    def get_new_version(self):
        """
        Create a new version associated with this index
        :return: version
        """
        version = IndexVersion(index=self, tag=codebase_id[:63])
        version.save()
        return version


@python_2_unicode_compatible
class IndexVersion(models.Model):
    """
    Each IndexVersion corresponds with an Elasticsearch index
    created with a particular schema. When the schema change,
    a IndexVersion is added to the table, and a new Elasticsearch
    index is created with that schema.
    """
    index = models.ForeignKey(Index)
    json = models.TextField(verbose_name="Elasticsearch Index JSON", blank=True)
    json_md5 = models.CharField(verbose_name="Elasticsearch Index JSON hash", db_index=True, max_length=32, editable=False)
    tag = models.CharField(verbose_name="Codebase Git Tag", max_length=64, blank=True)
    inserted = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "id"

    def __init__(self, *args, **kwargs):
        super(IndexVersion, self).__init__(*args, **kwargs)
        self._es_dsl_index = None

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<IndexVersion, ID: {}>'.format(self.id)

    @property
    def is_active(self):
        return self.id == self.index.active_version.id

    @property
    def name(self):
        return "{base_name}-{id}".format(base_name=self.index.name, id=self.id)

    def get_es_index(self):
        if not self.index:
            raise ValueError("get_es_index requires an Index to be associated with the IndexVersion")
        if not self.id:
            raise ValueError("get_es_index is only available on an IndexVersion that has been saved")
        if not self._es_dsl_index:
            self._es_dsl_index = ES_DSL_Index(name=self.name, using=es_client)
        return self._es_dsl_index

    def add_doc_type(self, doc_type, save=False):
        index = self.get_es_index()
        index.doc_type(doc_type)
        if save:
            self.json_md5, self.json = get_index_hash_and_json(index)
            self.save()


@python_2_unicode_compatible
class IndexAction(models.Model):
    """
    Each Action is a record of a bulk change to a particular
    Elasticsearch Index Version, for example, creating,
    updating, etc. To create a new IndexAction,
    create a new element in ACTIONS and then
    subclass this model with a proxy model, filling in
    perform_action().
    """

    STATUS_QUEUED = 'queued'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETE = 'complete'
    STATUSES_ALL = {STATUS_QUEUED, STATUS_IN_PROGRESS, STATUS_COMPLETE}
    STATUSES_ALL_CHOICES = [(i, i) for i in STATUSES_ALL]

    ACTION_CREATE_INDEX = 'create_index'
    ACTIONS_ALL = {ACTION_CREATE_INDEX}
    ACTIONS_ALL_CHOICES = [(i, i) for i in ACTIONS_ALL]

    DEFAULT_ACTION = ACTION_CREATE_INDEX

    # creates a `status` field with default as the first value in list: `queued`
    status = models.CharField(choices=STATUSES_ALL_CHOICES, max_length=32, default=STATUS_QUEUED)
    action = models.CharField(choices=ACTIONS_ALL_CHOICES, max_length=64)
    index = models.ForeignKey(Index)
    log = models.TextField(blank=True)
    # override TimeFramedModel.start to add on creation
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True)
    index_version = models.ForeignKey(IndexVersion, null=True)

    def __init__(self, *args, **kwargs):
        action = self._meta.get_field('action')
        action.default = self.DEFAULT_ACTION
        super(IndexAction, self).__init__(*args, **kwargs)

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<IndexAction, ID: {}>'.format(self.id)

    @property
    def dem_index(self):
        return getattr(self, '_dem_index', None)

    def add_log(self, msg, commit=True):
        print(msg)
        self.log = "{old_log}\n{msg}".format(old_log=self.log, msg=msg)
        if commit:
            self.save()

    def perform_action(self, dem_index, *args, **kwargs):
        """
        This is where subclasses implement the functionality that changes the index
        :return:
        """
        raise NotImplemented("override in subclasses")

    def to_in_progress(self):
        if self.status == self.STATUS_QUEUED:
            self.status = self.STATUS_IN_PROGRESS
            self.save()

    def to_complete(self):
        if self.status == self.STATUS_IN_PROGRESS:
            self.status = self.STATUS_COMPLETE
            self.end = datetime.datetime.now()
            self.save()

    def start_action(self, dem_index, *args, **kwargs):
        self._dem_index = dem_index
        index_name = dem_index.get_index_name()
        index_instance, _ = Index.objects.get_or_create(name=index_name)
        self.index = index_instance
        self.to_in_progress()
        self.perform_action(dem_index, *args, **kwargs)
        self.to_complete()

    @classmethod
    def get_new_action(cls, index_name, include_active_version=False, action=None):
        if not action:
            action = cls.DEFAULT_ACTION
        index_instance, _ = Index.objects.get_or_create(name=index_name)
        index_action = IndexAction(action=action, index=index_instance)

        if include_active_version and index_instance.active_version:
            index_action.index_version = index_instance.active_version

        index_action.save()
        return index_action


class CreateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_CREATE_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        """
        This is where subclasses implement the functionality that changes the index
        :return:
        """
        latest_version = self.index.get_latest_version()
        index_version = None
        created_new = False
        if latest_version:
            index_version = latest_version
        else:
            created_new = True
            index_version = self.index.get_new_version()

        self.index_version = index_version
        index_version.add_doc_type(dem_index.doc_type())
        es_index = index_version.get_es_index()

        schema_hash, _ = get_index_hash_and_json(es_index)

        msg = ""

        if created_new:
            # https://elasticsearch-py.readthedocs.io/en/master/api.html#elasticsearch.client.IndicesClient.create
            es_index.create()
            msg = (
                "The schema for {name} changed; created a new "
                "index in elasticsearch."
            )

        if latest_version.json_md5 != schema_hash:
            es_index.create()
            msg = (
                "The schema for {name} changed; created a new "
                "index in elasticsearch."
            )
        else:
            msg = (
                "the index schema has not changed since {name} "
                "was created; not creating a new index."
            )

        if msg:
            self.add_log(msg.format(name=index_version.name), True)
