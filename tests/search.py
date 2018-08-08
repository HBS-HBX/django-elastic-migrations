from __future__ import (absolute_import, division, print_function, unicode_literals)

from contextlib import contextmanager

from django.conf import settings
from elasticsearch_dsl import Text, Q, analyzer, token_filter, tokenizer

from django_elastic_migrations.indexes import DEMIndex, DEMDocType, DEMIndexManager
from tests.models import Movie

basic_analyzer = analyzer(
    "basic", filter=[token_filter("standard"), token_filter("lowercase"), token_filter("asciifolding")],
    tokenizer=tokenizer("standard"),
    type="custom")

alternate_textfield = Text(analyzer=basic_analyzer, search_analyzer=basic_analyzer)


class GenericDocType(DEMDocType):
    full_text = Text(required=True)
    full_text_boosted = Text(required=True)

    @classmethod
    def get_search_document_instance(cls, model):
        return cls(
            meta={'id': cls.get_model_id(model)},
            full_text=cls.get_model_full_text(model),
            full_text_boosted=cls.get_model_full_text_boosted(model),
        )

    @classmethod
    def get_reindex_iterator(cls, queryset):
        """
        returns an iterator where each item is a DocType instance dict
        for elasticsearch to index, complete with the id.
        :param queryset
        :return: iterator of GenericDocType.to_dict(include_meta=True)
        """
        user_docs = [
            cls.get_document(u) for u in queryset
        ]
        return [u for u in user_docs if u]

    @classmethod
    def get_document(cls, model):
        return cls.get_search_document_instance(model).to_dict(include_meta=True)

    @classmethod
    def get_model_id(cls, model):
        return model.id or None

    @classmethod
    def get_model_full_text(cls, model):
        return ''

    @classmethod
    def get_model_full_text_boosted(cls, model):
        return ''

    @classmethod
    def get_search(cls, search_query):
        full_text_query = cls.get_full_text_search_query(search_query)
        es_search = cls.search().query(full_text_query)
        return es_search

    @classmethod
    def get_full_text_search_query(cls, search_query):
        """
        :param search_query: the query to search for in full text and full text boosted fields
        :return: elasticsearch_dsl.query.Q
        """
        return Q(
            "multi_match",
            query=search_query,
            type="phrase",
            fields=[
                "full_text_boosted^2",
                "full_text",
            ]
        )


MovieSearchIndex = DEMIndex('movies')
MovieSearchIndex.settings(**settings.ELASTICSEARCH_INDEX_SETTINGS)


@MovieSearchIndex.doc_type
class MovieSearchDoc(GenericDocType):

    @classmethod
    def get_queryset(cls, last_updated_datetime=None):
        qs = Movie.objects.all()
        if last_updated_datetime:
            qs = qs.filter(last_modified__gte=last_updated_datetime)
        return qs

    @classmethod
    def get_model_full_text(cls, model):
        full_text = ""
        for field in ['genere', 'director', 'writer', 'actors', 'plot', 'production', 'title']:
            full_text = "{} {}".format(full_text, field)
        return full_text

    @classmethod
    def get_model_full_text_boosted(cls, model):
        return model.title


class DefaultNewSearchDocTypeMixin(GenericDocType):
    """
    Used by get_new_search_index() in the case that doc_type_mixin is not supplied
    """

    @classmethod
    def get_queryset(cls, last_updated_datetime=None):
        qs = Movie.objects.all()
        if last_updated_datetime:
            qs = qs.filter(last_modified__gte=last_updated_datetime)
        return qs


@contextmanager
def get_new_search_index(name, doc_type_mixin=None, create_and_activate=True, dem_index=None):
    """
    Given an index name and a class definition, create a new temporary index and associate it
    with a new doctype. This is a temporary index, so it's implemented as a context
    manager, so we can remove the index when done.

    Do not use the name "movies" or any other non-transient index name; it will interfere with it if so.

    :param name: base name of the index - not "movies" - something preferably unique
    :param cls: parameters of GenericDocType to override
    :param doc_type_mixin: a class to mix in to the generated doctype
    :param create_and_activate: if True, call DEMIndexManager.initialize(True, True) before returning
    :return: DEMIndex, DEMDocType
    """
    if name == "movies":
        raise ValueError("Don't use the movies index for testing; it will interfere with the fixture")

    if doc_type_mixin is None:
        doc_type_mixin = DefaultNewSearchDocTypeMixin

    my_new_index = dem_index
    if my_new_index is None:
        my_new_index = DEMIndex(name)
        my_new_index.settings(**settings.ELASTICSEARCH_INDEX_SETTINGS)

    class MyNewSearchDocType(doc_type_mixin, GenericDocType):
        pass

    my_new_index.doc_type(MyNewSearchDocType)

    if create_and_activate:
        DEMIndexManager.initialize(create_versions=True, activate_versions=True)
        # DEMIndexManager doesn't normally care about indexes that aren't declared in settings, so we have to add this manually
        DEMIndexManager.add_index(my_new_index)
        DEMIndexManager.reinitialize_esindex_instances()
        DEMIndexManager.create_index(name)
        DEMIndexManager.activate_index(name)

    yield (my_new_index, MyNewSearchDocType)

    # clean up after the index when we're done
    DEMIndexManager.destroy_dem_index(my_new_index)
