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

from django_elastic_migrations import codebase_id, es_client
from django_elastic_migrations.exceptions import NoActiveIndexVersion, NoCreatedIndexVersion


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
        return self.indexversion_set.filter(deleted_time__isnull=True).last()

    def get_new_version(self, dem_index=None):
        """
        Create a new version associated with this index.
        If a dem_index is supplied, use that dem index's
        json and hash.
        """
        version = IndexVersion(index=self, tag=codebase_id[:63])
        if dem_index:
            version.json_md5, version.json = dem_index.get_index_hash_and_json()
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
    # store the JSON sent to Elasticsearch to configure the index
    # note: the index name field in this field does NOT include the IndexVersion id
    json = models.TextField(verbose_name="Elasticsearch Index JSON", blank=True)
    # store an MD5 of the JSON field above, so as to compare equality
    json_md5 = models.CharField(verbose_name="Elasticsearch Index JSON hash", db_index=True, max_length=32,
                                editable=False)
    tag = models.CharField(verbose_name="Codebase Git Tag", max_length=64, blank=True)
    inserted = models.DateTimeField(auto_now_add=True)
    # TODO: add this deleted field in
    deleted_time = models.DateTimeField(null=True, blank=True)

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
        active_ver = self.index.active_version
        return active_ver and active_ver.id == self.id

    @property
    def name(self):
        return "{base_name}-{id}".format(base_name=self.index.name, id=self.id)

    def get_last_time_update_called(self):
        last_update = self.indexaction_set.filter(action=IndexAction.ACTION_UPDATE_INDEX).last()
        if last_update:
            return last_update.last_modified
        return None

    def delete(self, using=None, keep_parents=False):
        self.deleted_time = timezone.now()
        self.save()

    @property
    def is_deleted(self):
        return not self.deleted_time


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

    # linked models
    index = models.ForeignKey(Index)
    index_version = models.ForeignKey(IndexVersion, null=True)

    # which management command was run
    action = models.CharField(choices=ACTIONS_ALL_CHOICES, max_length=64)

    # timing of the management command
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(blank=True, null=True)
    last_modified = models.DateTimeField(auto_now=True)

    # state of this operation
    status = models.CharField(choices=STATUSES_ALL_CHOICES, max_length=32, default=STATUS_QUEUED)
    # text from management command
    log = models.TextField(blank=True)

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

    def add_log(self, msg, commit=True, use_self_dict_format=False):
        if use_self_dict_format:
            msg = msg.format(**self.__dict__)
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
        index_name = dem_index.get_base_name()
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
        force = kwargs.pop("force", False)
        new_version = None

        self.index_version = latest_version

        # configure self.__dict__ for format messages below
        self._index_name = self.index.name
        self._index_version_name = self.index_version.name

        msg = ""
        if latest_version and dem_index.hash_matches(latest_version.json_md5):
            if force:
                self.add_log(
                    "The doc type for index {_index_name} has not changed "
                    "since {_index_version_name}; but creating a new index anyway "
                    "since you added the --force argument",
                    use_self_dict_format=True
                ),
                self.index_version = dem_index.create()
                self._index_version_name = self.index_version.name
            else:
                self.add_log(
                    "The doc type for index {_index_name} has not changed "
                    "since {_index_version_name}; not creating a new index.",
                    use_self_dict_format=True
                )
        else:
            self.index_version = dem_index.create()
            self._index_version_name = self.index_version.name
            self.add_log(
                "The doc type for index {_index_name} changed; created a new "
                "index version {_index_version_name} in elasticsearch.",
                use_self_dict_format=True
            )


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
        reindex_iterator = dem_index.doc_type().get_reindex_iterator(last_update=last_update)

        # TODO: REMOVE THIS TESTING CODE (I don't want to reindex all documents while developing)
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
