# -*- coding: utf-8 -*-
"""
Database models for django_elastic_migrations.
"""

from __future__ import absolute_import, unicode_literals

import traceback

from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from elasticsearch.helpers import bulk
from elasticsearch_dsl import Index as ES_DSL_Index

from django_elastic_migrations import codebase_id, es_client
from django_elastic_migrations.exceptions import NoActiveIndexVersion, NoCreatedIndexVersion
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
    json_md5 = models.CharField(verbose_name="Elasticsearch Index JSON hash", db_index=True, max_length=32,
                                editable=False)
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

    def add_doc_type(self, doc_type, save=False, create=False):
        """
        Generate an elasticsearch Index instance associated with this
        index versions's name, and add the given doc_type to it.
        """
        index = self.get_es_index()
        index.doc_type(doc_type)
        if save:
            self.json_md5, self.json = get_index_hash_and_json(index)
            self.save()
        if create:
            index.create()

    def get_index_hash_and_json(self):
        return get_index_hash_and_json(self.get_es_index())

    def doc_type_matches_hash(self, doc_type):
        es_index = ES_DSL_Index(name=self.name, using=es_client)

        # back up the index already associated with the given doc_type (if any)
        index_backup = None
        _doc_type = getattr(doc_type, '_doc_type', None)
        _existing_index = None
        if _doc_type:
            _existing_index = getattr(_doc_type, 'index', None)
            if _existing_index:
                index_backup = None

        es_index.doc_type(doc_type)
        doc_type_hash, _ = get_index_hash_and_json(es_index)

        if _doc_type and _existing_index and index_backup:
            # restore the index already associated with the gijven doc type
            doc_type._doc_type.index = index_backup

        return self.json_md5 == doc_type_hash

    def get_last_time_update_called(self):
        last_update = self.indexaction_set.filter(action=IndexAction.ACTION_UPDATE_INDEX).last()
        if last_update:
            return last_update.last_modified
        return None


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
    STATUS_ABORTED = 'aborted'
    STATUSES_ALL = {STATUS_QUEUED, STATUS_IN_PROGRESS, STATUS_COMPLETE, STATUS_ABORTED}
    STATUSES_ALL_CHOICES = [(i, i) for i in STATUSES_ALL]

    ACTION_CREATE_INDEX = 'create_index'
    ACTION_UPDATE_INDEX = 'update_index'
    ACTION_ACTIVATE_INDEX = 'activate_index'
    ACTIONS_ALL = {ACTION_CREATE_INDEX, ACTION_UPDATE_INDEX, ACTION_ACTIVATE_INDEX}
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
            self.end = timezone.now()
            self.save()

    def to_aborted(self):
        self.status = self.STATUS_ABORTED
        self.end = timezone.now()
        self.save()

    def start_action(self, dem_index, *args, **kwargs):
        self._dem_index = dem_index
        index_name = dem_index.get_index_name()
        index_instance, _ = Index.objects.get_or_create(name=index_name)
        self.index = index_instance
        self.to_in_progress()
        try:
            self.perform_action(dem_index, *args, **kwargs)
        except Exception as ex:
            log_params = {
                "action": self.action,
                "doc": ex.__doc__ or "",
                "msg": ex.message,
                "stack": u''.join(traceback.format_stack())
            }
            msg = (
                u"While completing {action}, encountered exception: "
                u"\n - message: {msg} "
                u"\n - exception doc: {doc} "
                u"\n - exception stack: {stack} ".format(**log_params)
            )
            self.add_log(msg)
            self.to_aborted()
            raise ex

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
        latest_version = self.index.get_latest_version()
        new_version = None
        doc_type = dem_index.doc_type()
        doc_type_changed = False

        if latest_version and latest_version.doc_type_matches_hash(doc_type):
            self.index_version = latest_version
        if not self.index_version:
            new_version = self.index.get_new_version()
            self.index_version = new_version

        msg = ""

        if new_version:
            new_version.add_doc_type(doc_type, save=True, create=True)
            msg = (
                "The doc type for index {index_name} changed; created a new "
                "index version {index_version} in elasticsearch."
            )
        else:
            msg = (
                "The doc type for index {index_name} has not changed since {index_version}; "
                "not creating a new index."
            )

        if msg:
            self.add_log(msg.format(index_name=self.index.name, index_version=self.index_version.name), True)


class UpdateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_UPDATE_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        active_version = self.index.active_version
        if not active_version:
            msg = (
                "You must have an active version of the '{index_name}' index "
                "to call update index. Please activate an index and try again.".format(
                    index_name=self.index.name
                )
            )
            raise NoActiveIndexVersion(msg)

        self.index_version = active_version
        last_update = active_version.get_last_time_update_called()
        msg_params = {
            "index_version_name": active_version.name,
            "last_update": "never"
        }
        if last_update:
            msg_params.update({"last_update": str(last_update)})

        self.add_log(
            "Checking the last time update was called: "
            u"\n - index version: {index_version_name} "
            u"\n - update date: {last_update} ".format(**msg_params)
        )

        self.add_log("Getting Reindex Iterator...")
        reindex_iterator = dem_index.get_reindex_iterator(last_update)

        # testing
        from itertools import islice
        reindex_iterator = list(islice(reindex_iterator, 3))

        self.add_log("Calling bulk reindex...")
        bulk(client=es_client, actions=reindex_iterator, refresh=True)

        self.add_log("Completed with indexing {index_version_name}".format(**msg_params))


class ActivateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_ACTIVATE_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        latest_version = self.index.get_latest_version()
        msg_params = {"index_name": self.index.name}

        if not latest_version:
            raise NoCreatedIndexVersion(
                "You must have created a version of the '{index_name}' index "
                "to call activate index. Please create an index and "
                "try again.".format(**msg_params)
            )

        self.index.active_version = latest_version
        self.index_version = latest_version
        msg_params.update({"index_version_name": latest_version.name})
        self.index.save()

        self.add_log("Active version for {index_name} has been set "
                     "to {index_version_name}.".format(**msg_params))
