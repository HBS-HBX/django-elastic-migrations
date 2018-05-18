# coding=utf-8
import sys

from django.db import ProgrammingError
from elasticsearch_dsl import Index as ESIndex, DocType as ESDocType, Q as ESQ, Search

from django_elastic_migrations import es_client, environment_prefix
from django_elastic_migrations.exceptions import DEMIndexNotFound, DEMDocTypeRequiresGetReindexIterator, \
    IllegalDEMIndexState, DEMIndexVersionCodebaseMismatchError, NoActiveIndexVersion
from django_elastic_migrations.utils.es_utils import get_index_hash_and_json


"""
indexes.py - Django-facing API for interacting with this App

Module Conventions
------------------
* 'ES': classes imported from Elasticsearch are prefixed with this
* 'DEM': classes belonging to this app are prefixed with this (for Django Elastic Migrations)
"""


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
        base_name = dem_index_instance._base_name
        cls.instances[base_name] = dem_index_instance
        if cls.db_ready:
            return cls.get_index_model(base_name, create_on_not_found)

    @classmethod
    def class_db_init(cls):
        cls.db_ready = True
        if not ('makemigrations' in sys.argv or 'migrate' in sys.argv):
            cls.update_index_models()
        cls.reinitialize_esindex_instances()

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
    def get_dem_index(cls, index_name, use_version_mode=False):
        """
        Get the DEMIndex instance associated with `index_name`.
        :param index_name: Name of index
        :param use_version_mode: If True, treat `index_name` as the
               fully qualified elasticsearch name of the index
        :return:
        """
        version_number = None
        if use_version_mode and index_name:
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
        return s.query(ESQ('match_all')).count()

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
        cls.class_db_init()

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
        :param force_new: create a new index even if the schema is unchanged
        :return:
        """
        # avoid circular import
        from django_elastic_migrations.models import CreateIndexAction
        action = CreateIndexAction(force=force)
        return cls._start_action_for_indexes(action, index_name, use_version_mode=False)

    @classmethod
    def update_index(cls, index_name, use_version_mode=False):
        """
        Given the named index, update the documents. By default, it only
        updates since the time of the last update.
        :param index_name:
        :param all - whether or not to update all indexes
        :return:
        """
        # avoid circular import
        from django_elastic_migrations.models import UpdateIndexAction
        action = UpdateIndexAction()
        return cls._start_action_for_indexes(action, index_name, use_version_mode)

    @classmethod
    def activate_index(cls, index_name, use_version_mode=False, deactivate=False):
        """
        Given the named index, activate the latest version of the index
        """
        # avoid circular import
        from django_elastic_migrations.models import ActivateIndexAction
        action = ActivateIndexAction(deactivate=deactivate)
        return cls._start_action_for_indexes(action, index_name, use_version_mode)

    @classmethod
    def clear_index(cls, index_name, use_version_mode=False):
        """
        Given the named index, clear the documents from the index

        """
        # avoid circular import
        from django_elastic_migrations.models import ClearIndexAction
        action = ClearIndexAction()
        return cls._start_action_for_indexes(action, index_name, use_version_mode)

    @classmethod
    def drop_index(cls, index_name, use_version_mode=False, force=False):
        """
        Given the named index, drop it from es
        :param force - if True, drop an index even if the version is not supplied
        """
        # avoid circular import
        from django_elastic_migrations.models import DropIndexAction
        action = DropIndexAction(force=force)
        return cls._start_action_for_indexes(action, index_name, use_version_mode)

    @classmethod
    def _start_action_for_indexes(cls, action, index_name, use_version_mode=False):
        """
        Called by create_index, activate_index, update_index, clear_index, drop_index.

        This helper method is used for all actions that can receive one of the
        common index specifiers. See the "Methods To Specify Indexes" in
        "./manage.py es" for more info on the common ways they are specified.
        :param action: action to run
        :param index_name: either the base name or the fully qualified es index name,
               depending on use_version_mode
        :param use_version_mode: if true, separate the version id from the base name
               in the index_name
        """
        if index_name:
            dem_indexes = []
            if index_name == 'all':
                dem_indexes.extend(cls.get_indexes())
            else:
                dem_index = cls.get_dem_index(index_name, use_version_mode)
                if dem_index:
                    dem_indexes.append(dem_index)
                else:
                    DEMIndexNotFound(index_name)
            if dem_indexes:
                actions = []
                for dem_index in dem_indexes:
                    action.start_action(
                        dem_index=dem_index, use_version_mode=use_version_mode)
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
    Django users subclass DEMDocType instead of of Elasticsearch's DocType
    to use Django Elastic Migrations. All documentation from their class
    applies here.
    https://elasticsearch-dsl.readthedocs.io/en/latest/api.html#elasticsearch_dsl.DocType

    Change from Elasticsearch: we manage the doc type's index name to
    make it the activated version of the index by default.
    """

    def __init__(self, *args, **kwargs):
        super(DEMDocType, self).__init__(*args, **kwargs)
        # super.__init__ creates the self._doc_type property that we
        # modify here
        self._doc_type = _DEMDocTypeIndexHandler(
            getattr(self, '_doc_type', None))

    @classmethod
    def get_reindex_iterator(self, last_updated_datetime=None):
        """
        Django users override this method. It must return an iterator
        or generator of instantiated DEMDocType subclasses, ready
        for inserting into Elasticsearch. For example:

        class UsersDocType(DEMDocType)

            @classmethod
            def get_reindex_iterator(cls, last_updated_datetime=None):
                if last_updated_datetime:
                    users = User.objects.filter(
                        last_modified__gte=last_updated_datetime)
                else:
                    User.objects.all()
                return [cls.getDocForUser(u) for u in users]

        :param last_updated_datetime: DateTime
        :return: iterator / generator of *DEMDocType instances*
        """
        raise DEMDocTypeRequiresGetReindexIterator()


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
        :param use_version_mode: if True bypass whether or not this version
               is activated; use the name of the index directly
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
