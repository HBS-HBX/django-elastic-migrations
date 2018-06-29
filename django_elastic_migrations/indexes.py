# coding=utf-8
from __future__ import print_function
import sys

from django.db import ProgrammingError
from elasticsearch import TransportError
from elasticsearch.helpers import expand_action, bulk
from elasticsearch_dsl import Index as ESIndex, DocType as ESDocType, Q as ESQ, Search

from django_elastic_migrations import es_client, environment_prefix, es_test_prefix, dem_index_paths, get_logger
from django_elastic_migrations.exceptions import DEMIndexNotFound, DEMDocTypeRequiresGetReindexIterator, \
    IllegalDEMIndexState, DEMIndexVersionCodebaseMismatchError, NoActiveIndexVersion, DEMDocTypeRequiresGetQueryset
from django_elastic_migrations.utils.es_utils import get_index_hash_and_json
from django_elastic_migrations.utils.loading import import_module_element

"""
indexes.py - Django-facing API for interacting with Django Elastic Migrations

Module Conventions
------------------
* 'ES': classes imported from Elasticsearch are prefixed with this
* 'DEM': classes belonging to this app are prefixed with this (for Django Elastic Migrations)
"""


logger = get_logger()


class DEMIndexManager(object):
    """
    API for interacting with a collection of DEMIndexes.
    Called by Django Elastic Migrations management commands.
    """

    post_migrate_completed = False
    db_ready = False

    """
    DEMIndex base name ⤵
        django_elastic_migrations.models.Index instance
    """
    index_models = {}

    """
    DEMIndex base name ⤵ 
        active DEMIndex instance
    """
    instances = {}

    @classmethod
    def add_index(cls, dem_index_instance, create_on_not_found=True):
        base_name = dem_index_instance.get_base_name()
        cls.instances[base_name] = dem_index_instance
        if cls.db_ready:
            return cls.get_index_model(base_name, create_on_not_found)

    @classmethod
    def create_and_activate_version_for_each_index_if_none_is_active(
        cls, create_versions, activate_versions):
        for index_base_name, dem_index in cls.get_indexes_dict().items():
            if not cls.get_active_index_version(index_base_name):
                if create_versions:
                    # by default this will not create if not changed
                    cls.create_index(index_base_name)
                if activate_versions:
                    cls.activate_index(index_base_name)

    @classmethod
    def initialize(cls, create_versions=False, activate_versions=False):
        """
        Configure DEMIndexManager, loading settings from the database.
        :param create_versions: if True, create a version if settings
               have been changed.
        :param activate_versions: if True, activate the latest version
               iff none are active.
        """
        cls.db_ready = True
        try:
            migrating = 'makemigrations' in sys.argv or 'migrate' in sys.argv
            if not migrating:
                cls.update_index_models()
            for dem_index_path in dem_index_paths:
                dem_index = import_module_element(dem_index_path)
                cls.add_index(dem_index)
            cls.reinitialize_esindex_instances()
            if not migrating and (create_versions or activate_versions):
                cls.create_and_activate_version_for_each_index_if_none_is_active(
                    create_versions, activate_versions)
        except ProgrammingError as e:
            code, msg = e.args
            if code == 1146:
                # non critical; can happen during normal business operation
                logger.warning(
                    "Detected an attempt to initialize Django Elastic Migrations "
                    "without calling ./manage.py migrate to initialize it. Please "
                    "be sure to call migrate before using elasticsearch with it."
                )

    @classmethod
    def create_index_model(cls, base_name):
        if cls.db_ready:
            from django_elastic_migrations.models import Index as DEMIndexModel
            try:
                index_model = DEMIndexModel.objects.create(name=base_name)
                cls.index_models[base_name] = index_model
            except ProgrammingError:
                # the app is starting up and the database isn't available
                pass

    @classmethod
    def delete_es_created_index(cls, full_index_version_name, **kwargs):
        """
        Simple way to delete an index in Elasticsearch. Uses the raw ES client,
        so the full elasticsearch name of the index is required.
        :param full_index_version_name: name of elasticsearch index to delete
        :param kwargs: **kwargs
        """
        return es_client.indices.delete(index=full_index_version_name, **kwargs)

    @classmethod
    def get_active_index_version(cls, index_base_name):
        model_version = cls.get_index_model(index_base_name)
        if model_version:
            active_version = model_version.active_version
            if active_version:
                return active_version
        return None

    @classmethod
    def get_active_index_version_name(cls, index_base_name):
        active_version = cls.get_active_index_version(index_base_name)
        if active_version:
            return active_version.name
        return ""

    @classmethod
    def get_dem_index(cls, index_name, exact_mode=False):
        """
        Get the DEMIndex instance associated with `index_name`.
        :param index_name: Name of index
        :param exact_mode: If True, treat `index_name` as the
               fully qualified elasticsearch name of the index
        :return:
        """
        version_number = None
        if exact_mode and index_name:
            separator_index = index_name.rindex("-")
            base_name = index_name[:separator_index]
            version_number = index_name[separator_index+1:]
            index_name = base_name
        if version_number:
            return DEMIndex(index_name, version_id=version_number)
        return cls.get_indexes_dict().get(index_name, None)

    @classmethod
    def get_es_index_doc_count(cls, full_index_version_name, **kwargs):
        s = Search(index=full_index_version_name, using=es_client, **kwargs)
        try:
            return s.query(ESQ('match_all')).count()
        except TransportError as ex:
            if ex.status_code == 404:
                return 0
            else:
                raise ex

    @classmethod
    def get_index_model(cls, base_name, create_on_not_found=True):
        """
        Retrieves the Index Model for the given index base name from
        the DB. The Index Model is the Django Model that stores info
        about what Indexes are declared and which Index Versions are
        available.
        :param base_name: the base name of the index
        :param create_on_not_found: create a base index if one if not
               found in the DB. This does not impact elasticsearch,
               because an Index Model is an abstract parent of
               Index Versions, which are the concrete indexes in ES.
        :return: django_elastic_migrations.models.Index
        """
        index_model = cls.index_models.get(base_name)
        if not index_model:
            cls.update_index_models()
            index_model = cls.index_models.get(base_name)
            if not index_model and create_on_not_found:
                cls.create_index_model(base_name)
        return index_model

    @classmethod
    def get_indexes(cls):
        return cls.instances.values()

    @classmethod
    def get_indexes_dict(cls):
        return cls.instances

    @classmethod
    def list_es_created_indexes(cls):
        """
        Get the names of the available elasticsearch indexes
        :return: list(str)
        """
        return [i for i in es_client.indices.get_alias("*")]

    @classmethod
    def post_migrate(cls, sender, **kwargs):
        cls.post_migrate_completed = True
        cls.initialize()

    @classmethod
    def register_dem_index(cls, dem_index):
        cls.instances[dem_index.get_base_name()] = dem_index

    @classmethod
    def reinitialize_esindex_instances(cls):
        """
        When Elasticsearch Index classes are loaded into the
        python interpreter, the index name is set before
        we can read the active index version from the DB.
        After our django-elastic-migrations app is ready
        to talk to the DB and find out the names of the indexes,
        go through and reinitialize each ES Index subclass instance
        as well as their associated ES DocType subclasses
        with the appropriate index names
        """
        for index_base_name, instance in cls.instances.items():
            instance_doc_type = instance.doc_type()
            instance.__init__(index_base_name)
            instance.doc_type(instance_doc_type)

    @classmethod
    def test_pre_setup(cls):
        DEMIndexManager.initialize()
        cls.test_post_teardown()
        DEMIndexManager.create_index('all', force=True)
        DEMIndexManager.activate_index('all')
        DEMIndexManager.initialize()

    @classmethod
    def test_post_teardown(cls):
        DEMIndexManager.drop_index(
            'all', force=True, just_prefix=es_test_prefix)

    @classmethod
    def update_index_models(cls):
        if cls.db_ready:
            from django_elastic_migrations.models import Index as DEMIndexModel
            try:
                cls.index_models = {i.name: i for i in DEMIndexModel.objects.all()}
            except ProgrammingError:
                # the app is starting up and the database isn't available
                pass

    """
    Management Command APIs
    The section below contains helper methods for 
    Django Elastic Migrations' management commands.
    """

    @classmethod
    def create_index(cls, index_name, force=False):
        """
        If the index name is in the initialized indexes dict,
        and the Index does not exist, create the specified Index
        and the first IndexVersion.

        If the Index and a prior IndexVersion already exist, check
        that the schema has changed. If the schema has changed, create a new
        IndexVersion and associate it with the Index.

        If the schema has not changed since the last IndexVersion, raise
        DEMCannotCreateUnchangedIndexException.
        :param index_name: the base name of the index
        :param force: create a new index even if the schema is unchanged
        :return:
        """
        # avoid circular import
        from django_elastic_migrations.models import CreateIndexAction
        action = CreateIndexAction(force=force)
        return cls._start_action_for_indexes(action, index_name, exact_mode=False)

    @classmethod
    def update_index(cls, index_name, exact_mode=False, newer_mode=False, resume_mode=False):
        """
        Given the named index, update the documents. By default, it only
        updates since the time of the last update.
        :param index_name: the name to use
        :param exact_mode: whether to take index name as the literal es index name
        :param resume_mode: if True, only update items that have changed since last update index
        """
        # avoid circular import
        from django_elastic_migrations.models import UpdateIndexAction
        action = UpdateIndexAction(newer_mode=newer_mode, resume_mode=resume_mode)
        return cls._start_action_for_indexes(action, index_name, exact_mode)

    @classmethod
    def activate_index(cls, index_name, exact_mode=False):
        """
        Given the named index, activate the latest version of the index
        """
        # avoid circular import
        from django_elastic_migrations.models import ActivateIndexAction
        action = ActivateIndexAction()
        return cls._start_action_for_indexes(action, index_name, exact_mode)

    @classmethod
    def deactivate_index(cls, index_name, exact_mode=False):
        """
        Given the named index, activate the latest version of the index
        """
        # avoid circular import
        from django_elastic_migrations.models import DeactivateIndexAction
        action = DeactivateIndexAction()
        return cls._start_action_for_indexes(action, index_name, exact_mode)

    @classmethod
    def clear_index(cls, index_name, exact_mode=False, older_mode=False):
        """
        Given the named index, clear the documents from the index

        """
        # avoid circular import
        from django_elastic_migrations.models import ClearIndexAction
        action = ClearIndexAction(older_mode=older_mode)
        return cls._start_action_for_indexes(action, index_name, exact_mode)

    @classmethod
    def drop_index(
        cls, index_name, exact_mode=False, force=False, just_prefix=None, older_mode=False):
        """
        Given the named index, drop it from es
        :param force - if True, drop an index even if the version is not supplied
        :param just_prefix - if a string is supplied, only those index versions with the
               prefix will be dropped
        """
        # avoid circular import
        from django_elastic_migrations.models import DropIndexAction
        action = DropIndexAction(force=force, just_prefix=just_prefix, older_mode=older_mode)
        return cls._start_action_for_indexes(action, index_name, exact_mode)

    @classmethod
    def _start_action_for_indexes(cls, action, index_name, exact_mode=False):
        """
        Called by create_index, activate_index, update_index, clear_index, drop_index.

        This helper method is used for all actions that can receive one of the
        common index specifiers. See the "Methods To Specify Indexes" in
        "./manage.py es" for more info on the common ways they are specified.
        :param action: action to run
        :param index_name: either the base name or the fully qualified es index name,
               depending on exact_mode
        :param exact_mode: if true, separate the version id from the base name
               in the index_name
        """
        if index_name:
            dem_indexes = []
            if index_name == 'all':
                dem_indexes.extend(cls.get_indexes())
            else:
                dem_index = cls.get_dem_index(index_name, exact_mode)
                if dem_index:
                    dem_indexes.append(dem_index)
                else:
                    DEMIndexNotFound(index_name)
            if dem_indexes:
                actions = []
                for dem_index in dem_indexes:
                    action.start_action(dem_index=dem_index)
                    actions.append(action)
                return actions
        raise DEMIndexNotFound()


class _DEMDocTypeIndexHandler(object):
    """
    Internally, Elasticsearch-dsl-py uses a string stored in the
    DocType to determine which index to write to. This class is
    added to our subclass of DocType below in order to make it so
    that the .index property gets redirected to the value of the
    active index version for that doc type. All other attributes
    are handled by the original DocTypeOptions class.
    Not meant to be used directly outside of this module.
    """

    def __init__(self, es_doc_type):
        self.__es_doc_type = es_doc_type

    def __getattribute__(self, item):
        try:  # get attribute from this class
            return object.__getattribute__(self, item)
        except AttributeError as e:
            try:  # get attribute from Elasticsearch's DocTypeOptions class
                caught_item = object.__getattribute__(self.__es_doc_type, item)
                if item == 'index':
                    # if we're trying to get the `index` from DocTypeOptions,
                    # the value would be the "base name" of the index, which
                    # we use to look up the specific version of the index we
                    # have activated.
                    index_base_name = caught_item
                    if index_base_name:
                        active_index_name = DEMIndexManager.get_active_index_version_name(index_base_name)
                        if active_index_name:
                            return active_index_name
                return caught_item
            except AttributeError:
                pass
        return None


class DEMDocType(ESDocType):
    """
    Django users subclass DEMDocType instead of Elasticsearch's DocType
    to use Django Elastic Migrations. All documentation from their class
    applies here.
    https://elasticsearch-dsl.readthedocs.io/en/latest/api.html#elasticsearch_dsl.DocType

    Change from Elasticsearch: we manage the doc type's index name to
    make it the activated version of the index by default.
    """

    """
    The default size of batches to bulk index at once. 
    Higher batch sizes require more memory on the indexing server.
    """
    BATCH_SIZE = 100

    def __init__(self, *args, **kwargs):
        super(DEMDocType, self).__init__(*args, **kwargs)
        # super.__init__ creates the self._doc_type property that we
        # modify here
        self._doc_type = _DEMDocTypeIndexHandler(
            getattr(self, '_doc_type', None))

    @classmethod
    def get_reindex_iterator(cls, queryset):
        """
        Django users override this method. It must return an iterator
        or generator of instantiated DEMDocType subclasses, ready
        for inserting into Elasticsearch. For example:

        class UsersDocType(DEMDocType)

            @classmethod
            def get_reindex_iterator(cls, queryset):
                return [cls.getDocForUser(u) for user in queryset]

        :param queryset: queryset of objects to index; result of get_queryset()
        :return: iterator / generator of *DEMDocType instances*
        """
        raise DEMDocTypeRequiresGetReindexIterator()

    @classmethod
    def get_queryset(cls, last_updated_datetime=None):
        """
        Django users override this method. It must return a sliceable entity
        that will be subdivided in cls.generate_batches()
        :param last_updated_datetime:
        :return:
        """
        raise DEMDocTypeRequiresGetQueryset()

    @classmethod
    def generate_batches(cls, qs=None, batch_size=BATCH_SIZE, total_items=None):
        """
        Divide a queryset into batches of BATCH_SIZE entities.
        If this is an unevaluated django queryset,
        the result will be a list of unevaluated querysets.
        :param qs:
        :param batch_size:
        :param total_items:
        :return: list of unevaluated QuerySets
        """
        if qs is None:
            qs = cls.get_queryset()

        if total_items is None:
            try:
                total_items = qs.count()
            except AttributeError:
                total_items = len(qs)

        batches = []
        for i in range(0, total_items, batch_size):
            # See https://docs.djangoproject.com/en/1.9/ref/models/querysets/#when-querysets-are-evaluated:
            # "slicing an unevaluated QuerySet returns another unevaluated QuerySet"
            batches.append(qs[i:i + batch_size])
        return batches

    @classmethod
    def get_bulk_indexing_kwargs(cls):
        """
        Override this method to tune parameters to the bulk indexing command:
        https://elasticsearch-py.readthedocs.io/en/master/helpers.html?highlight=bulk#elasticsearch.helpers.streaming_bulk
        :return: kwargs object
        """
        return {
            "chunk_size": 500,
            "max_chunk_bytes": 100 * 1024 * 1024,
            "raise_on_error": True,
            "expand_action_callback": expand_action,
            "raise_on_exception": True,
            "max_retries": 0,
            "initial_backoff": 2,
            "max_backoff": 600,
            "yield_ok": True
        }

    @classmethod
    def bulk_index(cls, reindex_iterator):
        """
        Execute Elasticsearch's bulk indexing helper, passing in the result of
        cls.get_bulk_indexing_kwargs()
        :param reindex_iterator: an iterator of DocType instances from cls.get_reindex_iterator()
        :return: (num_success, num_failed)
        """
        kwargs = cls.get_bulk_indexing_kwargs()
        success, failed = bulk(
            client=es_client, actions=reindex_iterator, refresh=True, stats_only=True,
            **kwargs
        )
        return success, failed

    @classmethod
    def batched_bulk_index(cls, last_updated_datetime=None, before_batch_cb=None, after_batch_cb=None):
        queryset = cls.get_queryset(last_updated_datetime)

        try:
            total_items = queryset.count()
        except AttributeError:
            total_items = len(queryset)

        batches = cls.generate_batches(qs=queryset, total_items=total_items)
        num_batches = len(batches)
        for batch_num, batch_queryset in enumerate(batches, 1):
            before_batch_cb(batch_num, num_batches, total_items)

            reindex_iterator = cls.get_reindex_iterator(batch_queryset)
            success, failed = cls.bulk_index(reindex_iterator)

            after_batch_cb(success, failed, batch_num, num_batches, total_items)


class DEMIndex(ESIndex):
    """
    Django users subclass DEMIndex instead of elasticsearch-dsl-py's Index
    to use Django Elastic Migrations. Most documentation from their class
    applies here.

    Change from Elasticsearch: several convenience methods were
    """

    def __init__(self, name, using=es_client, version_id=None):
        """
        :param name: the name of this index
        :param using: the elasticsearch client to use
        """
        prefixed_name = "{}{}".format(environment_prefix, name)
        super(DEMIndex, self).__init__(prefixed_name, using)
        self.__prefixed_name = prefixed_name
        self.__base_name = name
        self.__doc_type = None
        self.__version_id = version_id
        self.__version_model = None

        # if this DEMIndex has a version_id, and .doc_type() has been called,
        # then this property will be filled in with a reference to the
        # original DEMIndex, the one in the codebase.
        # it's not used outside of .doc_type().
        self.__base_dem_index = None

        if not version_id:
            # ensure every index calls home to our manager
            DEMIndexManager.register_dem_index(self)

    def clear(self):
        """
        Remove all of the documents in this index.
        """
        self.search().query(ESQ('match_all')).delete()

    def create(self, **kwargs):
        """
        Overrides elasticsearch_dsl.Index.create().
        Creates a new IndexVersion record, adding the json schema
        of the new index to it. Then calls create on the new
        index for elasticsearch.
        :returns new django_elastic_migrations.models.IndexVersion
        :see also https://elasticsearch-dsl.readthedocs.io/en/latest/api.html#elasticsearch_dsl.Index.create
        """
        index_model = self.get_index_model()
        if not index_model:
            index_model = DEMIndexManager.add_index(self)
            if not index_model:
                raise ValueError("DEMIndex.create couldn't create {}".format(
                    self.get_base_name()))
        index_version = index_model.get_new_version(self)
        try:
            index = index_version.name
            body = self.to_dict()
            self.connection.indices.create(index=index, body=body, **kwargs)
        except Exception as ex:
            if isinstance(ex, TransportError):
                if ex.status_code == 400:
                    # "resource_already_exists_exception"
                    return index_version
            index_version.delete()
            raise ex
        return index_version

    def delete(self, **kwargs):
        index_version = self.get_version_model()
        DEMIndexManager.delete_es_created_index(index_version.name, ignore=[400, 404])
        if index_version:
            index_version.delete()

    def doc_type(self, doc_type=None):
        """
        Overrides elasticsearch_dsl.Index.doc_type().
        Associates a DEMDocType with this DEMIndex, which is a bidirectional
        association.

        In the case that this DEMIndex has been instantiated
        as DEMIndex(name, version_id) and attempting to retrieve a doc_type:
        IF the index version requires a different version of the codebase,
        this method will raise DEMIndexVersionCodebaseMismatchError.

        :returns DEMDocType associated with this DEMIndex (if any)
        """
        if doc_type:
            self.__doc_type = doc_type
            return super(DEMIndex, self).doc_type(doc_type)
        else:
            if self.get_version_id() and not self.__doc_type:
                version_model = self.get_version_model()
                self.__base_dem_index = DEMIndexManager.get_dem_index(self.get_base_name())
                doc_type = self.__base_dem_index.doc_type()
                doc_type_index_backup = doc_type._doc_type.index
                doc_type._doc_type.index = version_model.name
                self.__doc_type = super(DEMIndex, self).doc_type(doc_type)
                if not self.hash_matches(version_model.json_md5):
                    doc_type._doc_type.index = doc_type_index_backup
                    self.__doc_type = None
                    msg = (
                        "Someone requested DEMIndex {index_name}, "
                        "which was created in codebase version {tag}. "
                        "The current version of that index does not have the same "
                        "spec. Please run operations for {index_name} on an app "
                        "server running a version such as {tag}.  "
                        " - needed doc type hash: {needed_hash}".format(
                            index_name=version_model.name,
                            needed_hash=version_model.json_md5,
                            tag=version_model.tag
                        )
                    )
                    raise DEMIndexVersionCodebaseMismatchError(msg)
            return self.__doc_type

    def get_active_version_index_name(self):
        return DEMIndexManager.get_active_index_version_name(self.__base_name)

    def get_base_name(self):
        return self.__base_name

    def get_index_hash_and_json(self):
        """
        Get the schema json for this index and its hash for this index.
        Note: the schema only contains the base name, even though it
        will be accessed through an index version.
        :return: (md5 str, json string)
        """
        es_index = self.clone(name=self.__base_name, using=es_client)
        return get_index_hash_and_json(es_index)

    def get_index_model(self):
        return DEMIndexManager.get_index_model(self.__base_name, False)

    def get_num_docs(self):
        return self.search().query(ESQ('match_all')).count()

    def get_version_id(self):
        return self.__version_id or 0

    def get_version_model(self):
        """
        If this index was instantiated with an id, return the VersionModel associated
        with it. If not, return the active version index name
        :return:
        """
        version_id = self.get_version_id()
        if version_id:
            if not self.__version_model:
                # importing here to avoid circular imports
                from django_elastic_migrations.models import IndexVersion
                self.__version_model = IndexVersion.objects.filter(
                    id=self.get_version_id()
                ).first()
            return self.__version_model
        return self.get_index_model().active_version

    def hash_matches(self, their_index_hash):
        our_index_hash, _ = self.get_index_hash_and_json()
        return our_index_hash == their_index_hash

    def save(self):
        try:
            super(DEMIndex, self).save()
        except ValueError as ex:
            if "Empty value" in ex.message and not self.get_active_version_index_name():
                msg = (
                    "{base_name} does not have an activated index version. "
                    "Please activate one to save a document. "
                    "\n sample command: ./manage.py es_activate {base_name}"
                    "\n original error message: {err_msg}".format(
                        base_name=self.get_base_name(),
                        err_msg=ex.message
                    )
                )
                raise NoActiveIndexVersion(msg)

    @property
    def _name(self):
        """
        Override Elasticsearch's super._name attribute, which determines
        which ES index is written to, with our dynamic name that
        takes into account the active index version. This property
        is read in the superclass.
        """
        version_id = self.get_version_id()
        if version_id:
            version_model = self.get_version_model()
            if version_model:
                return version_model.name
            raise IllegalDEMIndexState("No associated version found in the database for {}-{}".format(
                self.get_base_name(), version_id))
        return self.get_active_version_index_name()

    @_name.setter
    def _name(self, value):
        """
        Override Elasticsearch's super._name attribute, which determines
        which ES index is written to, with our dynamic name
        This property is written to by the superclass.
        """
        self.__base_name = value
