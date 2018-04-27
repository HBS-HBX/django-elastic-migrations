from django.core.exceptions import ImproperlyConfigured
from elasticsearch_dsl import DocType


def validate_index_class(cls):
    name = cls.get_index_name()
    if not name:
        raise ImproperlyConfigured("This class must have a `name` property or implement get_index_name()")
    doc_type = cls.get_doc_type()
    if not issubclass(doc_type, DocType):
        raise ImproperlyConfigured("This class must have a `doc_type` property or implement `get_doc_type()` returning elasticsearch_dsl.DocType")
    return True


class ESSearchIndex(object):

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


indexes = {}


class ESIndexManager(object):

    @classmethod
    def initialize_indexes(cls):
        from django_elastic_migrations.models import IndexMaster
        actual_indexes = {i.name: i for i in IndexMaster.objects.all()}
        for ESIndex in ESSearchIndex.__subclasses__():
            if validate_index_class(ESIndex):
                index = None
                index_name = ESIndex.get_index_name()
                if index_name in actual_indexes:
                    index = ESIndex(model=actual_indexes[index_name])
                else:
                    index = ESIndex()
                if index:
                    indexes[index.name] = index
        return indexes

    @classmethod
    def list_indexes(self):
        return indexes.values()
