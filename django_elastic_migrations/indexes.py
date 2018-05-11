# coding=utf-8
import sys

from django.db import ProgrammingError
from elasticsearch_dsl import Index as ESIndex, DocType as ESDocType

from django_elastic_migrations import es_client
from django_elastic_migrations.exceptions import DEMIndexNotFound
from django_elastic_migrations.utils.es_utils import get_index_hash_and_json


class DEMIndexManager(object):
    """
    API for interacting with a collection of DEMIndexes.
    Called by various management commands.
    """

    post_migrate_completed = False
    db_ready = False

    """
    DEMIndex base name ⤵ 
        DEMIndex instance
    """
    instances = {}

    """
    DEMIndex base name ⤵
        django_elastic_migrations.models.Index instance
    """
    index_models = {}

    @classmethod
    def post_migrate(cls, sender, **kwargs):
        cls.post_migrate_completed = True
        cls.class_db_init()

    @classmethod
    def class_db_init(cls):
        cls.db_ready = True
        if not ('makemigrations' in sys.argv or 'migrate' in sys.argv):
            # if we just
            cls.update_index_models()
        cls.reinitialize_esindex_instances()

    @classmethod
    def add_index(cls, dem_index_instance, create_on_not_found=True):
        base_name = dem_index_instance._base_name
        cls.instances[base_name] = dem_index_instance
        if cls.db_ready:
            return cls.get_index_model(base_name, create_on_not_found)

    @classmethod
    def list_es_created_indexes(cls):
        """
        Get the names of the available elasticsearch indexes
        :return: list(str)
        """
        return [i for i in es_client.indices.get_alias("*")]

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
    def update_index_models(cls):
        if cls.db_ready:
            from django_elastic_migrations.models import Index as DEMIndexModel
            try:
                cls.index_models = {i.name: i for i in DEMIndexModel.objects.all()}
            except ProgrammingError:
                # the app is starting up and the database isn't available
                pass

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
    def get_active_index_version_name(cls, index_base_name):
        model_version = cls.get_index_model(index_base_name)
        if model_version:
            active_version = model_version.active_version
            if active_version:
                return active_version.name
        return ""

    @classmethod
    def register_dem_index(cls, dem_index):
        cls.instances[dem_index.get_base_name()] = dem_index

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
    def get_indexes(cls):
        return cls.instances.values()

    @classmethod
    def get_indexes_dict(cls):
        return cls.instances

    @classmethod
    def get_dem_index(cls, index_name):
        return cls.get_indexes_dict().get(index_name, None)

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
        DEMCannotCreateUnchangedIndexException
        :param index_name: the base name of the index
        :param force_new: create a new index even if the schema is unchanged
        :return:
        """
        index_class = cls.get_dem_index(index_name)
        if index_class:
            from django_elastic_migrations.models import CreateIndexAction
            CreateIndexAction().start_action(dem_index=index_class, force=force)
        else:
            raise DEMIndexNotFound(index_name)

    @classmethod
    def update_index(cls, index_name):
        """
        Given the named index, update the documents
        :param index_name:
        :return:
        """
        dem_index = cls.get_dem_index(index_name)
        if dem_index:
            from django_elastic_migrations.models import UpdateIndexAction
            UpdateIndexAction().start_action(dem_index=dem_index)
        else:
            raise DEMIndexNotFound(index_name)

    @classmethod
    def activate_index(cls, index_name):
        """
        Given the named index, activate the latest version of the index
        """
        dem_index = cls.get_dem_index(index_name)
        if dem_index:
            from django_elastic_migrations.models import ActivateIndexAction
            ActivateIndexAction().start_action(dem_index=dem_index)
        else:
            raise DEMIndexNotFound(index_name)


class DEMDocTypeIndexHandler(object):
    """
    Internally, Elasticsearch-dsl-py uses a string stored in the
    DocType to determine which index to write to. This class is
    added to our subclass of DocType below in order to make it so
    that the .index property gets redirected to the value of the
    active index version for that doc type. All other attributes
    are handled by the original DocTypeOptions class.
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
    SubClass of Elasticsearch's DocType, used to specify the
    types of fields that will be put into the mapping of a
    specific index. The functionality changed from Elasticsearch
    is that we manage the doc type's index name.
    """

    def __init__(self, *args, **kwargs):
        super(DEMDocType, self).__init__(*args, **kwargs)
        self._doc_type = DEMDocTypeIndexHandler(getattr(self, '_doc_type', None))


class DEMIndex(ESIndex):
    """
    Subclass of Elasticsearch's Index which specifies the
    base name of a new index.
    """

    def __init__(self, name, using=es_client):
        super(DEMIndex, self).__init__(name, using)
        self._base_name = name
        self.__doc_type = None
        # ensure every index calls home to the index manager
        DEMIndexManager.register_dem_index(self)

    def create(self, **kwargs):
        """
        Create a new IndexVersion record, adding the json schema
        of the new index to it. Then call create on the new
        index for elasticsearch.
        :returns new django_elastic_migrations.models.IndexVersion
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

    def doc_type(self, doc_type=None):
        if doc_type:
            self.__doc_type = doc_type
            return super(DEMIndex, self).doc_type(doc_type)
        else:
            return self.__doc_type

    def get_active_version_index_name(self):
        # return self.get_index_model().active_version.name
        return DEMIndexManager.get_active_index_version_name(self._base_name)

    def get_base_name(self):
        return self._base_name

    def get_index_hash_and_json(self):
        """
        Get the schema json for this index and its hash for this index.
        Note: the schema only contains the base name, even though it
        will be accessed through an index version.
        :return: (md5 str, json string)
        """
        es_index = self.clone(name=self._base_name, using=es_client)
        return get_index_hash_and_json(es_index)

    def get_index_model(self):
        return DEMIndexManager.get_index_model(self._base_name, False)

    def hash_matches(self, their_index_hash):
        our_index_hash, _ = self.get_index_hash_and_json()
        return our_index_hash == their_index_hash

    @property
    def _name(self):
        """
        Override super._name attribute, which determines which ES index is
        written to, with our dynamic name that takes into account
        the active index version. This property
        is read by the superclass.
        """
        return self.get_active_version_index_name()

    @_name.setter
    def _name(self, value):
        """
        When we call super.__init__, the first action is to write
        to super._name attribute. Instead, store the value in
        _base_name so as to look up the real name of the
        active index later.
        """
        self._base_name = value
