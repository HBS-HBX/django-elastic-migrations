from __future__ import (absolute_import, division, print_function, unicode_literals)
from django.conf import settings
from elasticsearch_dsl import Text, Q

from django_elastic_migrations.indexes import DEMIndex, DEMDocType
from tests.models import Movie


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
