# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function, unicode_literals)

import datetime
import json
import sys
import time
import traceback
from multiprocessing import cpu_count

import os
import random
from django.db import models, transaction
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from elasticsearch import TransportError

from django_elastic_migrations import codebase_id, environment_prefix, DEMIndexManager
from django_elastic_migrations.exceptions import NoActiveIndexVersion, NoCreatedIndexVersion, IllegalDEMIndexState, \
    CannotDropActiveVersion, IndexVersionRequired, CannotDropOlderIndexesWithoutForceArg
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger
from django_elastic_migrations.utils.multiprocessing_utils import USE_ALL_WORKERS

logger = get_logger()


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
        return self.indexversion_set.filter(deleted_time__isnull=True, prefix=environment_prefix).last()

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

    def _get_other_versions(
        self, given_version=None, prefix=environment_prefix, older=True):
        """
        Find all non-deleted versions that are older / newer
        than the given version. If older is False, return newer
        versions.
        """
        qs = self.get_available_versions()
        if prefix:
            qs = self.get_available_versions_with_prefix(prefix)

        target_id = 0
        if given_version:
            target_id = given_version.id
        elif self.active_version_id:
            target_id = self.active_version_id

        if older:
            return qs.filter(id__lt=target_id)
        return qs.filter(id__gt=target_id)

    def get_older_versions(self, given_version=None, prefix=environment_prefix):
        """
        Find all non-deleted versions that are older than the given version
        """
        return self._get_other_versions(given_version, prefix, older=True)

    def get_newer_versions(self, given_version=None, prefix=environment_prefix):
        """
        Find all non-deleted versions that are older than the given version
        """
        return self._get_other_versions(given_version, prefix, older=False)


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

    def get_last_time_update_called(self, before_action=None):
        qs = self.indexaction_set.filter(
            action=IndexAction.ACTION_UPDATE_INDEX,
            status=IndexAction.STATUS_COMPLETE,
            index_version=self.id
        )
        if before_action:
            qs.filter(id__lt=before_action.id)
        last_update = qs.last()
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
    STATUSES_ALL = [STATUS_QUEUED, STATUS_IN_PROGRESS, STATUS_COMPLETE, STATUS_ABORTED]
    STATUSES_ALL_CHOICES = [(i, i) for i in STATUSES_ALL]

    ACTION_CREATE_INDEX = 'create_index'
    ACTION_UPDATE_INDEX = 'update_index'
    ACTION_ACTIVATE_INDEX = 'activate_index'
    ACTION_DEACTIVATE_INDEX = 'deactivate_index'
    ACTION_CLEAR_INDEX = 'clear_index'
    ACTION_DROP_INDEX = 'drop_index'
    ACTION_PARTIAL_UPDATE_INDEX = 'partial_update_index'
    ACTIONS_ALL = [
        ACTION_CREATE_INDEX, ACTION_UPDATE_INDEX, ACTION_ACTIVATE_INDEX,
        ACTION_DEACTIVATE_INDEX, ACTION_CLEAR_INDEX, ACTION_DROP_INDEX, ACTION_PARTIAL_UPDATE_INDEX
    ]
    ACTIONS_ALL_CHOICES = [(i, i) for i in ACTIONS_ALL]

    DEFAULT_ACTION = ACTION_CREATE_INDEX

    # linked models
    index = models.ForeignKey(Index)
    index_version = models.ForeignKey(IndexVersion, null=True)

    # if this IndexAction has a parent IndexAction, its id is here
    parent = models.ForeignKey("self", null=True, related_name="children")

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

    argv = models.CharField(max_length=1000, blank=True)

    docs_affected = models.IntegerField(default=0)

    task_kwargs = models.TextField(verbose_name="json of kwargs to pass to action", default="{}")

    def __init__(self, *args, **kwargs):
        action = self._meta.get_field('action')
        action.default = self.DEFAULT_ACTION
        self.verbosity = kwargs.pop('verbosity', 1)
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
        if commit and 'test' not in sys.argv:
            self.save()

    def add_logs(self, msgs, commit=True, use_self_dict_format=False, level=logger.INFO):
        for msg in msgs:
            self.add_log(msg, commit=False, use_self_dict_format=use_self_dict_format, level=level)
        if commit and 'test' not in sys.argv:
            self.save()

    def perform_action(self, dem_index, *args, **kwargs):
        """
        This is where subclasses implement the functionality that changes the index
        :return:
        """
        raise NotImplemented("override in subclasses")

    def to_in_progress(self):
        if self.status == self.STATUS_QUEUED:
            self.start = timezone.now()
            self.status = self.STATUS_IN_PROGRESS
            self.argv = " ".join(sys.argv)
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
            result = self.perform_action(dem_index, *args, **kwargs)
            self.to_complete()
            return result
        except Exception as ex:
            log_params = {
                "action": self.action,
                "doc": ex.__doc__ or "",
                "msg": str(ex),
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

    def add_to_parent_docs_affected(self, num_docs):
        """
        If this IndexAction has a parent IndexAction, atomically add the number of docs
        affected to the parent's docs affected
        :param num_docs: int, number of docs changed in Elasticsearch
        """
        parent_docs_affected = self.parent.docs_affected
        if self.parent and num_docs:
            with transaction.atomic():
                parent = (
                    IndexAction.objects.select_for_update()
                        .get(id=self.parent.id)
                )
                parent.docs_affected += num_docs
                parent_docs_affected = parent.docs_affected
                parent.save()
        return parent_docs_affected


"""
↓ Action Mixins Below ↓

Mixins are used to provide handling for common parameters
"""


# noinspection PyUnresolvedReferences
class GenericModeMixin(object):
    """
    Used to pop a kwarg off and attach it to self in an IndexAction
    """

    MODE_NAME = 'sample_mode'

    def __init__(self, *args, **kwargs):
        mode_val = kwargs.pop(self.MODE_NAME, False)
        setattr(self, self.MODE_NAME, mode_val)
        super(GenericModeMixin, self).__init__(*args, **kwargs)

    def _apply_to(self, versions, action):
        """
        Given the IndexVersions supplied, loop through each, starting the given
        IndexAction
        :param versions: iterable of IndexVersion
        :param action: an IndexAction
        """
        if not versions:
            self.add_log(
                'No {mode_name} versions found; no actions performed.'.format(
                    mode_name=self.MODE_NAME),
                level=logger.WARNING,
            )
            return

        self.add_log(
            "Applying action {action_name} to {num_index_versions} "
            "{mode_name} versions ...".format(
                action_name=action.action, num_index_versions=len(versions),
                mode_name=self.MODE_NAME
            ))

        for version in versions:
            sub_dem_index = DEMIndexManager.get_dem_index(version.name, exact_mode=True)
            action.start_action(dem_index=sub_dem_index)

        self.add_log(
            " - Done applying action {action_name} to {num_index_versions} "
            "{mode_name} versions".format(
                action_name=action.action, num_index_versions=len(versions),
                mode_name=self.MODE_NAME
            ))


class OlderModeMixin(GenericModeMixin):
    MODE_NAME = "older_mode"

    def apply_to_older(self, versions, action):
        self._apply_to(versions, action)


class NewerModeMixin(GenericModeMixin):
    MODE_NAME = "newer_mode"

    def apply_to_newer(self, versions, action):
        self._apply_to(versions, action)


"""
↓ Action Implementations Below ↓

Actions are in descending alphabetical order
"""


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
                    "Deactivating index version '{index_version_name}' "
                    "because you said to do so.".format(**msg_params))
            else:
                index.active_version = version_model
                self.add_log(
                    "Activating index version '{index_version_name}' "
                    "because you said to do so.".format(**msg_params))
            index.save()
            # by reinitializing, we ensure this worker knows about the update immediately
            DEMIndexManager.initialize()

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
                # by reinitializing, we ensure this worker knows about the update immediately
                DEMIndexManager.initialize()
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


class ClearIndexAction(OlderModeMixin, IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_CLEAR_INDEX

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def perform_action(self, dem_index, *args, **kwargs):
        msg_params = {"index_name": self.index.name}
        if dem_index.get_version_id():
            # we have instantiated this DEMIndex with a specific IndexVersion
            version_model = dem_index.get_version_model()
            if self.older_mode:
                versions = self.index.get_older_versions(given_version=version_model)
                self.apply_to_older(versions, action=ClearIndexAction())
            else:
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
                if self.older_mode:
                    versions = self.index.get_older_versions(given_version=active_version)
                    self.apply_to_older(versions, action=ClearIndexAction())
                else:
                    msg_params.update({"index_version_name": latest_version.name})
                    dem_index.clear()
                    self.add_log(
                        "The active index for '{index_name}' is '{index_version_name}': "
                        "Clearing all documents because you said to do so.".format(
                            **msg_params))
            else:
                raise NoActiveIndexVersion(
                    "You must activate an index version to clear using the index "
                    "name `{index_version_name}` only.".format(**msg_params)
                )


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
                    "since '{_index_version_name}'... ",
                    use_self_dict_format=True
                )
                created = dem_index.create_if_not_in_es()
                if created:
                    self.add_log("   ... but it wasn't found in Elasticsearch! We recreated it there.")
                else:
                    self.add_log("  ... did not create a new index.")
        else:
            self.index_version = dem_index.create()
            self._index_version_name = self.index_version.name
            self.add_log(
                "The doc type for index '{_index_name}' changed; created a new "
                "index version '{_index_version_name}' in elasticsearch.",
                use_self_dict_format=True
            )


class DeactivateIndexAction(IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_DEACTIVATE_INDEX

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

            index.active_version = None
            if index.active_version == version_model:
                self.add_log(
                    "Deactivating formerly active index version "
                    "'{index_version_name}' "
                    "because you said to do so.".format(**msg_params))
                index.save()
                # re-initialize so as to ensure this worker gets the message
                DEMIndexManager.initialize()
            else:
                self.add_log(
                    "There is no need to deactivate '{index_version_name}' "
                    "because is it not active.".format(**msg_params))

        else:
            # use the active version of the index if one exists.

            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                raise NoCreatedIndexVersion(
                    "You must have created a version of the "
                    "'{index_name}' index to call es_deactivate "
                    "index.".format(**msg_params)
                )

            # at least one version is available.

            msg_params.update({"index_version_name": latest_version.name})

            if self.index.active_version:
                self.index.active_version = None
                self.add_log(
                    "For index '{index_name}', DEactivating "
                    "'{index_version_name}' "
                    "because you said so.".format(
                        **msg_params))
                self.index.save()
                # re-initialize so as to ensure this worker gets the message
                DEMIndexManager.initialize()
            else:
                self.add_log(
                    "For index '{index_name}', there is no active version; "
                    "so there is no version to deactivate. \n"
                    "No action performed.".format(**msg_params)
                )


class DropIndexAction(OlderModeMixin, IndexAction):
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
            if self.older_mode:
                versions = self.index.get_older_versions(
                    given_version=version_model, prefix=self.just_prefix)
                action = DropIndexAction(
                    force=self.force, just_prefix=self.just_prefix)
                self.apply_to_older(versions, action=action)
            else:
                self.index_version = version_model
                if version_model.is_active:
                    raise CannotDropActiveVersion()

                msg_params.update({"index_version_name": version_model.name})
                dem_index.delete()
                msg = ("Dropping index version '{index_version_name}' "
                       "because you said to do so.".format(**msg_params))
                self.add_log(msg)
        else:
            # first, check if *any* version exists.
            latest_version = self.index.get_latest_version()
            if not latest_version:
                self.add_log(
                    "There are no created versions of the '{index_name}' "
                    "elasticsearch index to drop! No action taken.".format(**msg_params)
                )
                return

            if not self.force:

                msg_params['sample_version_num'] = 123
                if self.index.active_version:
                    msg_params['sample_version_num'] = self.index.active_version_id
                if self.older_mode:
                    raise CannotDropOlderIndexesWithoutForceArg()
                else:
                    raise IndexVersionRequired(
                        "You asked to drop index {index_name}, \nbut it is required "
                        "to specify the exact index version you wish to drop. \n"
                        "Try, for example, "
                        "`./manage.py es_drop {index_name}-{sample_version_num} --exact`, \n"
                        "if version {sample_version_num} is the one you would like to drop.".format(
                            **msg_params
                        )
                    )

            available_versions = []
            if self.older_mode:
                versions = self.index.get_older_versions(
                    given_version=self.index.active_version, prefix=self.just_prefix)
                action = DropIndexAction(
                    force=self.force, just_prefix=self.just_prefix)
                return self.apply_to_older(versions, action=action)
            elif self.just_prefix:
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


class UpdateIndexAction(NewerModeMixin, IndexAction):
    DEFAULT_ACTION = IndexAction.ACTION_UPDATE_INDEX

    USE_ALL_WORKERS = 999

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def __init__(self, *args, **kwargs):
        self.resume_mode = kwargs.pop('resume_mode', False)
        # :param workers: number of workers to parallelize indexing
        self.workers = kwargs.pop('workers', 0)
        self.batch_size = kwargs.pop('batch_size', 0)
        self.start_date = kwargs.pop('start_date', None)
        super(UpdateIndexAction, self).__init__(*args, **kwargs)
        self._batch_num = 0
        self._expected_remaining = 0
        self._indexed_docs = 0
        self._num_batches = 0
        self._num_failed = 0
        self._num_success = 0
        self._total_items = 0
        self.docs_affected = 0

    def perform_action(self, dem_index, *args, **kwargs):
        self.prepare_action(dem_index)

        doc_type = dem_index.doc_type()

        self._last_update = None

        if self.start_date:
            self._last_update = self.start_date
            self.add_log(
                "--start detected; Using start date {_last_update}", use_self_dict_format=True
            )
        elif self.resume_mode:
            self._last_update = self.index_version.get_last_time_update_called(before_action=self)
            if not self._last_update:
                self._last_update = 'never'
            self.add_log(
                "--resume detected; Checking the last time update was called: "
                u"\n - index version: {_index_version_name} "
                u"\n - update date: {_last_update} ", use_self_dict_format=True
            )

        self.add_log("Starting batched bulk update ...")
        if self.batch_size:
            self.add_log("using manually specified batch size of {}".format(self.batch_size))
        else:
            self.batch_size = doc_type.BATCH_SIZE
            self.add_log("using class default batch size of {}".format(self.batch_size))

        if self.workers:
            self.workers = int(self.workers)
            self._num_vcpus = cpu_count()
            self.add_log("detected {_num_vcpus} logical cpus", use_self_dict_format=True)

            if self.workers == USE_ALL_WORKERS:
                self.workers = self._num_vcpus - 1
                if self.workers < 2:
                    self.workers = 1
                self.add_log("using multiprocessing with {workers} worker(s) out of {_num_vcpus} logcial CPUs", use_self_dict_format=True)

            else:
                self.add_log("using multiprocessing with {workers} worker(s)", use_self_dict_format=True)

        self.add_log(
            (
                "About to update index {_index_version_name}:\n"
                " # batch size: {batch_size}\n"
                " # workers: {workers}\n"
                " # verbosity: {verbosity}\n"
            ),
            use_self_dict_format=True
        )

        success, failed = doc_type.batched_bulk_index(
            last_updated_datetime=self._last_update,
            workers=self.workers,
            update_index_action=self,
            batch_size=self.batch_size,
            verbosity=self.verbosity
        )

        self.refresh_from_db()
        self._num_success, self._num_failed = success, failed
        self._indexed_docs = self._num_success + self._num_failed
        self.docs_affected = self._num_success

        child_statuses = self.children.values_list('status', flat=True)
        if all([c == IndexAction.STATUS_COMPLETE for c in child_statuses]):
            self.add_log("All child tasks are completed successfully")
        else:
            bad_children = list(self.children.exclude(status__in=IndexAction.STATUS_COMPLETE))
            if bad_children:
                err_logs = []
                for bad_child in bad_children:
                    err_logs.append("task id {} has status {}".format(bad_child.id, bad_child.status))
                self.add_logs(err_logs)
            else:
                self.add_logs("No child tasks found! Please ensure there was work to be done.", level=logger.WARNING)

        self._runtime = timezone.now() - self.start
        self._docs_per_sec = self._indexed_docs / self._runtime.total_seconds()

        runtimes = []
        docs_per_batch = []
        for child in self.children.all():
            delta = child.end - child.start
            runtimes.append(delta.total_seconds())
            docs_per_batch.append(child.docs_affected)

        self._avg_batch_runtime = 'unknown'
        if runtimes:
            self._avg_batch_runtime = str(datetime.timedelta(seconds=sum(runtimes) / len(runtimes)))

        self._avg_docs_per_batch = 'unknown'
        if docs_per_batch:
            self._avg_docs_per_batch = sum(docs_per_batch) / len(docs_per_batch)

        self.add_log(
            (
                "Completed updating index {_index_version_name}: \n"
                " # successful updates: {_num_success}\n"
                " # failed updates: {_num_failed}\n"
                " # total docs attempted to update: {_indexed_docs}\n"
                " # batch size: {batch_size}\n"
                " # batch avg num docs: {_avg_docs_per_batch}\n"
                " # batch avg runtime: {_avg_batch_runtime}\n"
                " # total runtime: {_runtime}\n"
                " # docs per second: {_docs_per_sec}\n"
                " # workers: {workers}\n"
                " # verbosity: {verbosity}\n"
            ),
            use_self_dict_format=True
        )

    def prepare_action(self, dem_index):
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

            if self.newer_mode:
                versions = self.index.get_newer_versions(given_version=index_version)
                self.apply_to_newer(versions, action=UpdateIndexAction())
            else:
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

            if self.newer_mode:
                versions = self.index.get_newer_versions(given_version=active_version)
                self.apply_to_newer(versions, action=UpdateIndexAction())
                # we're done, because the newer versions will get their own actions
                return

            # we have an active version for this index. now do the update.
            self.index_version = active_version
            self._index_version_name = self.index_version.name
            self.add_log(
                "Handling update of index '{_index_name}' using its active index version "
                "'{_index_version_name}'", use_self_dict_format=True)


class PartialUpdateIndexAction(UpdateIndexAction):
    """
    An IndexAction that updates a subset of the documents.
    Kwargs are saved in the database and can be refreshed.
    """

    DEFAULT_ACTION = IndexAction.ACTION_PARTIAL_UPDATE_INDEX
    REQUIRED_TASK_KWARGS = [
        "batch_num",
        "pks",
        "start_index",
        "end_index",
        "max_batch_num",
        "total_docs_expected",
        "batch_num_items",
        "verbosity",
        "max_retries",
        "workers"
    ]

    class Meta:
        # https://docs.djangoproject.com/en/2.0/topics/db/models/#proxy-models
        proxy = True

    def set_task_kwargs(self, kwargs):
        new_kwargs = {}
        for required_attribute in self.REQUIRED_TASK_KWARGS:
            new_kwargs[required_attribute] = kwargs[required_attribute]
        self.task_kwargs = json.dumps(new_kwargs)

    def perform_action(self, dem_index, *args, **kwargs):

        kwargs = json.loads(self.task_kwargs)

        self.prepare_action(dem_index)

        doc_type = dem_index.doc_type()

        start = kwargs["start_index"]
        end = kwargs["end_index"]
        self._workers = kwargs["workers"]
        self._total_docs_expected = kwargs["total_docs_expected"]
        verbosity = kwargs["verbosity"]
        max_retries = kwargs["max_retries"]
        self._batch_num = kwargs["batch_num"]
        self._start_index = start
        self._end_index = end
        self._max_batch_num = kwargs["max_batch_num"]
        self._pid = os.getpid()

        self.add_log(
            (
                "Starting with {_index_version_name} update batch {_batch_num}/{_max_batch_num}: \n"
                " # batch start index: {_start_index}\n"
                " # batch end index: {_end_index}\n"
                " # pid: {_pid}"
            ),
            use_self_dict_format=True
        )

        if self._workers and self._total_docs_expected:
            # ensure workers don't overload dbs by being sync'd up
            # if we're less than 10% done, put a little randomness
            # in between the workers to dither query load
            if (self.parent.docs_affected / self._total_docs_expected) < 0.1:
                time.sleep(random.random()*2)

        qs = doc_type.get_queryset()
        current_qs = qs[start:end]

        retries = 0
        success, failed = (0, 0)
        reindex_iterator = doc_type.get_reindex_iterator(current_qs)
        while retries < max_retries:
            try:
                success, failed = doc_type.bulk_index(reindex_iterator)
                if verbosity >= 2 and retries:
                    self.add_log('Completed indexing {} - {}, tried {}/{} times'.format(
                        start + 1, end, retries + 1, max_retries))
                break
            except Exception as exc:
                retries += 1
                error_context = {
                    'start': start + 1,
                    'end': end,
                    'retries': retries,
                    'max_retries': max_retries,
                    'pid': os.getpid(),
                    'exc': exc
                }
                error_msg = 'Failed indexing %(start)s - %(end)s (retry %(retries)s/%(max_retries)s): %(exc)s'
                error_msg += ' (pid %(pid)s): %(exc)s'
                if retries >= max_retries:
                    logger.error(error_msg, error_context, exc_info=True)
                    raise
                elif verbosity >= 2:
                    logger.warning(error_msg, error_context, exc_info=True)
                # If going to try again, sleep a bit before
                time.sleep(2 ** retries)

        self._num_success = success
        self.docs_affected = success
        self._num_failed = failed
        self._indexed_docs = success + failed

        self._parent_docs_affected = int(self.add_to_parent_docs_affected(success))
        self._parent_runtime = timezone.now() - self.parent.start
        self._runtime = timezone.now() - self.start

        self._total_docs_remaining = self._total_docs_expected - self._parent_docs_affected
        if self._parent_docs_affected:
            self._parent_docs_per_sec = self._parent_docs_affected / self._parent_runtime.total_seconds()
        else:
            self._parent_docs_per_sec = self._indexed_docs / self._runtime.total_seconds()

        self._total_docs_remaining_pct = 100 * self._total_docs_remaining // self._total_docs_expected
        self._parent_docs_affected_pct = 100 - self._total_docs_remaining_pct
        if self._parent_docs_per_sec:
            self._expected_parent_runtime = str(datetime.timedelta(
                seconds= self._total_docs_remaining / self._parent_docs_per_sec))
        else:
            self._expected_parent_runtime = 'unknown'

        self.add_log(
            (
                "Completed with {_index_version_name} update batch {_batch_num}/{_max_batch_num}: \n"
                " # batch successful updates: {_num_success}\n"
                " # batch failed updates: {_num_failed}\n"
                " # batch docs attempted to update: {_indexed_docs}\n"
                " # batch runtime: {_runtime}\n"
                " # parent total docs updated: {_parent_docs_affected} ({_parent_docs_affected_pct}%)\n"
                " # parent total docs expected: {_total_docs_expected}\n"
                " # parent total docs remaining: {_total_docs_remaining} ({_total_docs_remaining_pct}%)\n"
                " # parent estimated runtime remaining: {_expected_parent_runtime}\n"
                " # num workers {_workers}\n"
                " # pid: {_pid}\n"
            ),
            use_self_dict_format=True
        )
        return self._num_success, self._num_failed

    @staticmethod
    def do_partial_update(index_action_id):
        # importing here to avoid a circular loop
        index_action = PartialUpdateIndexAction.objects.get(id=index_action_id)
        index_version = index_action.index_version
        dem_index_exact_name = index_version.name
        dem_index = DEMIndexManager.get_dem_index(dem_index_exact_name, exact_mode=True)
        return index_action.start_action(dem_index)
