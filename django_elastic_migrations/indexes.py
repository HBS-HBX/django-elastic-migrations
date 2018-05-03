from django.core.exceptions import ImproperlyConfigured
from elasticsearch_dsl import DocType, Index

from django_elastic_migrations.exceptions import DEMIndexNotFound



class DEMIndex(object):
    """
    Class that the end user subclasses to specify what the base name
    of their index is and what the doc type instance is
    """

    name = None

    doc_type = None

    def __init__(self, model=None):
        self.model = model

    @classmethod
    def get_index_name(cls):
        return cls.name

    @classmethod
    def get_reindex_iterator(cls, updated_since=None):
        """
        Return an iterator of DocType instances
        ready for insertion into Elasticsearch. If updated_since
        is provided, return only those doc_types that have been
        modified since that time.
        """
        return []

    @classmethod
    def get_doc_type(cls):
        return cls.doc_type


def _validate_index_class(cls):
    name = cls.get_index_name()
    if not name:
        raise ImproperlyConfigured("This class must have a `name` property or implement get_index_name()")
    doc_type = cls.get_doc_type()
    if not issubclass(doc_type, DocType):
        raise ImproperlyConfigured("This class must have a `doc_type` property or implement `get_doc_type()` returning elasticsearch_dsl.DocType")
    return True


"""
This is the list of indexes that the programmer has specified by subclassing
DEMIndex in their code. It is initialied when the django_elastic_migrations
app ready method is called.
"""
_known_essearchindex_subclasses = {}
_initialized = 0


def _get_indexes(refresh=False):
    """
    For every class that extends DEMIndex, add an entry
    to the indexes database.
    :param refresh: if True, update the database even if it
    has already been initialized.
    :return: dictionary {index_name: DEMIndex instance
    """
    global _initialized, _known_essearchindex_subclasses

    if not _initialized or refresh:

        from django_elastic_migrations.models import Index
        actual_indexes = {i.name: i for i in Index.objects.all()}

        for DEMIndexJr in DEMIndex.__subclasses__():

            if _validate_index_class(DEMIndexJr):
                index = None
                index_name = DEMIndexJr.get_index_name()

                if index_name in actual_indexes:
                    index = DEMIndexJr(model=actual_indexes[index_name])

                else:
                    index = DEMIndexJr()

                if index:
                    _known_essearchindex_subclasses[index.name] = index

        _initialized += 1

    return _known_essearchindex_subclasses


class DEMIndexManager(object):
    """
    Class used to manipulate indexes defined
    """

    @classmethod
    def get_indexes(cls):
        return _get_indexes().values()

    @classmethod
    def get_indexes_dict(cls):
        return _get_indexes()

    @classmethod
    def get_dem_index(cls, index_name):
        return cls.get_indexes_dict().get(index_name, None)

    @classmethod
    def create_index(cls, index_name):
        """
        If the index name is in the initialized indexes dict,
        and the Index does not exist, create the specified Index
        and the first IndexVersion.

        If the Index and a prior IndexVersion already exist, check
        that the schema has changed. If the schema has changed, create a new
        IndexVersion and associate it with the Index.

        If the schema has not changed since the last IndexVersion, raise
        DEMCannotCreateUnchangedIndexException
        :param index_name:
        :return:
        """
        index_class = cls.get_dem_index(index_name)
        if index_class:
            from django_elastic_migrations.models import CreateIndexAction
            CreateIndexAction().start_action(dem_index=index_class)
        else:
            raise DEMIndexNotFound(index_name)
