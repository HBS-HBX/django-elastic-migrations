# -*- coding: utf-8 -*-
"""
Database models for django_elastic_migrations.
"""

from __future__ import absolute_import, unicode_literals

import sys
import traceback

from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from elasticsearch import TransportError
from elasticsearch.helpers import bulk

from django_elastic_migrations import codebase_id, es_client, environment_prefix
from django_elastic_migrations.exceptions import NoActiveIndexVersion, NoCreatedIndexVersion, IllegalDEMIndexState, \
    CannotDropActiveVersion, IndexVersionRequired
from django_elastic_migrations.utils.log import getLogger


logger = getLogger()


@python_2_unicode_compatible
class Index(models.Model):
    """
    Model that retains information about all Elasticsearch indexes
    managed by django_elastic_migrations
    """
    name = models.CharField(verbose_name="Index Name", max_length=32, unique=True)

    # Django convention is to use '+' for related name when you don't need the
    # reverse relation. in this case, we already have IndexVersion pointing
    # back to Index, so we don't need that reverse name.
    # See https://docs.djangoproject.com/en/2.0/ref/models/fields/#django.db.models.ForeignKey.related_name
    active_version = models.ForeignKey(
        'django_elastic_migrations.IndexVersion',
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
        version = IndexVersion(index=self, tag=codebase_id[:63], prefix=environment_prefix)
        if dem_index:
            version.json_md5, version.json = dem_index.get_index_hash_and_json()
        version.save()
        return version

    def deactivate(self):
        """
        Remove any active version from this index
        """
        if self.active_version:
            self.active_version = None
            self.save()

    def get_available_versions(self):
        return self.indexversion_set.filter(deleted_time__isnull=True)

    def get_available_versions_with_prefix(self, prefix=environment_prefix):
        return self.get_available_versions().filter(prefix=prefix)

    def get_nonactivated_versions(self):
        qs = self.get_available_versions()
        if self.active_version:
            return qs.exclude(id__in=[self.active_version.id])
        return qs


@python_2_unicode_compatible
class IndexVersion(models.Model):
    """
    Each IndexVersion corresponds with an Elasticsearch index
    created with a particular schema. When the schema change,
    a IndexVersion is added to the table, and a new Elasticsearch
    index is created with that schema.
    """
    index = models.ForeignKey(Index)
    prefix = models.CharField(verbose_name="Environment Prefix", max_length=32, blank=True)
    # store the JSON sent to Elasticsearch to configure the index
    # note: the index name field in this field does NOT include the IndexVersion id
    json = models.TextField(verbose_name="Elasticsearch Index JSON", blank=True)
    # store an MD5 of the JSON field above, so as to compare equality
    json_md5 = models.CharField(
        verbose_name="Elasticsearch Index JSON hash", db_index=True,
        max_length=32, editable=False)
    tag = models.CharField(verbose_name="Codebase Git Tag", max_length=64, blank=True)
    inserted = models.DateTimeField(auto_now_add=True)
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
        return '<IndexVersion for {}, ID: {}>'.format(str(self.index), self.id)

    @property
    def is_active(self):
        active_ver = self.index.active_version
        return active_ver and active_ver.id == self.id

    @property
    def is_deleted(self):
        return not self.deleted_time

    @property
    def name(self):
        return "{environment_prefix}{base_name}-{id}".format(
            environment_prefix=self.prefix,
            base_name=self.index.name, id=self.id)

    def get_last_time_update_called(self):
        last_update = self.indexaction_set.filter(
            action=IndexAction.ACTION_UPDATE_INDEX
        ).last()
        if last_update:
            return last_update.last_modified
        return None

    def delete(self, using=None, keep_parents=False):
        if self.is_active:
            parent_index = self.index
            parent_index.active_version = None
            parent_index.save()
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
    ACTION_DROP_INDEX = 'drop_index'
    ACTIONS_ALL = {ACTION_CREATE_INDEX, ACTION_UPDATE_INDEX, ACTION_ACTIVATE_INDEX, ACTION_DROP_INDEX}
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

    def add_log(self, msg, commit=True, use_self_dict_format=False, level=logger.INFO):
        if use_self_dict_format:
            msg = msg.format(**self.__dict__)
        logger.log(level, msg)
        self.log = "{old_log}\n{msg}".format(old_log=self.log, msg=msg)
        if commit and not 'test' in sys.argv:
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
            self.to_complete()
        except Exception as ex:
            log_params = {
                "action": self.action,
                "doc": ex.__doc__ or "",
                "msg": ex.message,
                "stack": u''.join(traceback.format_exc())
            }
            msg = (
                u"While completing {action}, encountered exception: "
                u"\n - message: {msg} "
                u"\n - exception doc: {doc} "
                u"\n - exception stack: {stack} ".format(**log_params)
            )
            self.add_log(msg, level=logger.ERROR)
            self.to_aborted()

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

    def __init__(self, *args, **kwargs):
        self.force = kwargs.pop('force', False)
        super(CreateIndexAction, self).__init__(*args, **kwargs)

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        latest_version = self.index.get_latest_version()

        self._index_name = self.index.name

        msg = ""
        if latest_version and dem_index.hash_matches(latest_version.json_md5):
            self.index_version = latest_version
            self._index_version_name = self.index_version.name
            if self.force:
                self.add_log(
                    "The doc type for index '{_index_name}' has not changed "
                    "since '{_index_version_name}'; "
                    "\nbut creating a new index anyway since you added "
                    "the --force argument!",
                    use_self_dict_format=True
                ),
                self.index_version = dem_index.create()
                self._index_version_name = self.index_version.name
            else:
                self.add_log(
                    "The doc type for index '{_index_name}' has not changed "
                    "since '{_index_version_name}'; not creating a new index.",
                    use_self_dict_format=True
                )
        else:
            self.index_version = dem_index.create()
            self._index_version_name = self.index_version.name
            self.add_log(
                "The doc type for index '{_index_name}' changed; created a new "
                "index version '{_index_version_name}' in elasticsearch.",
                use_self_dict_format=True
            )


class UpdateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_UPDATE_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        self._index_name = self.index.name
        self._index_version_id = dem_index.get_version_id()

        if self._index_version_id:
            # we have instantiated this DEMIndex with a specific IndexVersion
            index_version = dem_index.get_version_model()
            if not index_version:
                msg = (
                    "DEMIndex '{_index_name}' configured with version "
                    "'{_index_version_id}' did not have an IndexModel "
                    "in the database".format(**self.__dict__)
                )
                raise IllegalDEMIndexState(msg)

            self.index_version = index_version
            self._index_version_name = index_version.name
            self.add_log(
                "Handling update of manually specified index version "
                "'{_index_version_name}'", use_self_dict_format=True)

        else:
            # use the active version of the index if one exists.

            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                raise NoCreatedIndexVersion(
                    "You must have created and activated a version of the "
                    "'{_index_name}' index to call update "
                    "index.".format(**self.__dict__)
                )

            # at least one version is available. now get the *active* version for this index.
            active_version = self.index.active_version

            if not active_version:
                msg = (
                    "You must have an active version of the '{_index_name}' index "
                    "to call update index. Please activate an index and try again.".format(
                        **self.__dict__
                    )
                )
                raise NoActiveIndexVersion(msg)

            # we have an active version for this index. now do the update.
            self.index_version = active_version
            self._index_version_name = self.index_version.name
            self.add_log(
                "Handling update of index '{_index_name}' using its active index version "
                "'{_index_version_name}'", use_self_dict_format=True)

        doc_type = dem_index.doc_type()

        self._last_update = self.index_version.get_last_time_update_called()
        if not self._last_update:
            self._last_update = 'never'
        self.add_log(
            "Checking the last time update was called: "
            u"\n - index version: {_index_version_name} "
            u"\n - update date: {_last_update} ", use_self_dict_format=True
        )

        self.add_log("Getting Reindex Iterator...")

        reindex_iterator = doc_type.get_reindex_iterator(
            last_update=self._last_update)

        # TODO: REMOVE THIS TESTING CODE (I don't want to reindex all documents while developing)
        from itertools import islice
        reindex_iterator = list(islice(reindex_iterator, 3))

        self.add_log("Calling bulk reindex...")
        bulk(client=es_client, actions=reindex_iterator, refresh=True)

        self.add_log("Completed with indexing {_index_version_name}", use_self_dict_format=True)


class ActivateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_ACTIVATE_INDEX

    def __init__(self, *args, **kwargs):
        self.deactivate = kwargs.pop('deactivate', False)
        super(ActivateIndexAction, self).__init__(*args, **kwargs)

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        msg_params = {"index_name": self.index.name}
        if dem_index.get_version_id():
            # we have instantiated this DEMIndex with a specific IndexVersion
            version_model = dem_index.get_version_model()
            msg_params.update({"index_version_name": version_model.name})
            self.index_version = version_model
            index = self.index

            if self.deactivate and index.active_version == version_model:
                index.active_version = None
                self.add_log(
                    "DEactivating index version '{index_version_name}' "
                    "because you said to do so.".format(**msg_params))
            else:
                index.active_version = version_model
                self.add_log(
                    "Activating index version '{index_version_name}' "
                    "because you said to do so.".format(**msg_params))
            index.save()

        else:
            # use the active version of the index if one exists.

            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                raise NoCreatedIndexVersion(
                    "You must have created a version of the "
                    "'{index_name}' index to call es_activate "
                    "index.".format(**msg_params)
                )

            # at least one version is available. now get the *active* version for this index.
            active_version = self.index.active_version
            msg_params.update({"index_version_name": latest_version.name})

            if self.deactivate:
                if self.index.active_version:
                    self.index.active_version = None
                    self.add_log(
                        "For index '{index_name}', DEactivating "
                        "'{index_version_name}' "
                        "because you said so.".format(
                            **msg_params))
                    self.index.save()
                else:
                    self.add_log(
                        "For index '{index_name}', there is no active version; "
                        "so there is no version to deactivate. \n"
                        "No action performed.".format(**msg_params)
                    )
            elif active_version != latest_version:
                self.index.active_version = latest_version
                self.index.save()
                self.add_log(
                    "For index '{index_name}', activating '{index_version_name}' "
                    "because you said so.".format(
                        **msg_params))
            else:
                self.add_log(
                    "For index '{index_name}', '{index_version_name}' "
                    "is the latest index version and it is already active. "
                    "No action taken. ".format(
                        **msg_params))


class ClearIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_ACTIVATE_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        msg_params = {"index_name": self.index.name}
        if dem_index.get_version_id():
            # we have instantiated this DEMIndex with a specific IndexVersion
            version_model = dem_index.get_version_model()
            self.index_version = version_model
            msg_params.update({"index_version_name": version_model.name})
            dem_index.clear()
            msg = ("Cleared all documents from index version '{index_version_name}' "
                   "because you said to do so.".format(**msg_params))
            self.add_log(msg)
        else:
            # use the active version of the index if one exists.

            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                raise NoCreatedIndexVersion(
                    "You must have created a version of the "
                    "'{index_name}' index to call clear "
                    "index.".format(**msg_params)
                )

            # at least one version is available. now get the *active* version for this index.
            active_version = self.index.active_version
            if active_version:
                self.index_version = latest_version
                msg_params.update({"index_version_name": latest_version.name})
                dem_index.clear()
                self.add_log(
                    "The active index for '{index_name}' is '{index_version_name}': "
                    "Clearing all documents because you said to do so.".format(
                        **msg_params))
            else:
                raise NoActiveIndexVersion(
                    "You must activate an index version to clear using the index "
                    "name `{index_version_name}`only.".format(**msg_params)
                )


class DropIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_DROP_INDEX

    def __init__(self, *args, **kwargs):
        self.force = kwargs.pop('force', False)
        self.just_prefix = kwargs.pop('just_prefix', None)
        super(DropIndexAction, self).__init__(*args, **kwargs)

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        msg_params = {"index_name": self.index.name}
        if dem_index.get_version_id():
            # we have instantiated this DEMIndex with a specific IndexVersion
            version_model = dem_index.get_version_model()
            self.index_version = version_model
            if version_model.is_active:
                raise CannotDropActiveVersion()

            msg_params.update({"index_version_name": version_model.name})
            dem_index.delete()
            msg = ("Dropping index version '{index_version_name}' "
                   "because you said to do so.".format(**msg_params))
            self.add_log(msg)
        else:
            if not self.force:
                raise IndexVersionRequired(
                    "You asked to drop index {index_name}, \nbut it is required "
                    "to specify the exact index version you wish to drop. \n"
                    "Try, for example, "
                    "`./manage.py es_drop {index_name}-6 --mode=version`, \n"
                    "if version 6 is the one you would like to drop.".format(
                        **msg_params
                    )
                )

            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                self.add_log(
                    "There are no created versions of the '{index_name}' "
                    "elasticsearch index to drop! No action taken.".format(**msg_params)
                )
                return

            available_versions = []
            if self.just_prefix:
                available_versions = self.index.get_available_versions_with_prefix(self.just_prefix)
            else:
                available_versions = self.index.get_available_versions()
            self.add_log(
                "About to drop {} versions because you said to do so "
                "with the argument --force!".format(
                    len(available_versions),
                )
            )

            # avoid circular import
            from django_elastic_migrations import DEMIndexManager
            count = 0

            for version in available_versions:
                count += 1
                self.add_log(
                    "Dropping version {} because you said to do so "
                    "with the argument --force!".format(
                        version.name
                    )
                )
                try:
                    DEMIndexManager.delete_es_created_index(version.name)
                    version.delete()
                except TransportError as ex:
                    if ex.status_code == 404:
                        self.add_log(
                            "Version {} does not exist in ES; not doing anything there".format(
                                version.name
                            )
                        )
                        if version.is_deleted:
                            self.add_log(
                                "Version {} was already deleted in IndexVersion model; "
                                "not doing anything further".format(
                                    version.name
                                )
                            )
                            count -= 1
                        else:
                            version.delete()
                    else:
                        raise ex

            self.add_log("Done dropping {} versions.".format(count))
