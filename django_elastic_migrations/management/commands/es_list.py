from typing import NamedTuple

from texttable import Texttable

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.exceptions import FirstMigrationNotRunError
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger

log = get_logger()

"""
Data model for making a row of the output table from ./manage.py es_list
"""
EsListRow = NamedTuple(
    'EsListRow', [
        ('index_base_name', str),
        ('index_version_name', str),
        ('created', int),
        ('active', int),
        ('docs', int),
        ('tag', str),
    ]
)


class Command(ESCommand):
    help = "django-elastic-migrations: list available indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_exact=False, default_all=True)
        parser.add_argument(
            '--es-only', action='store_true',
            help="Only list indexes in elasticsearch, without respect to the models."
        )

    def handle(self, *args, **options):
        log.info("Available Index Definitions:")

        indexes, _, apply_all, _, _ = self.get_index_specifying_options(
            options, require_one_include_list=['es_only'])

        es_only = options.get('es_only', False)

        table = Texttable(max_width=85)
        if es_only:

            table.header(["Name", "Count"])
            [table.add_row(row) for row in DEMIndexManager.list_es_doc_counts().items()]

        else:

            indexes = DEMIndexManager.get_indexes()

            if indexes and not apply_all:
                new_indexes = []
                for index in indexes:
                    if index.get_base_name() in options['index']:
                        new_indexes.append(index)
                indexes = new_indexes

            rows = []
            try:
                for dem_index in indexes:
                    dem_index_model = dem_index.get_index_model()
                    index_versions = dem_index_model.get_available_versions_with_prefix()
                    row = None
                    if index_versions:
                        for index_version in index_versions:
                            num_docs = DEMIndexManager.get_es_index_doc_count(index_version.name)
                            row = EsListRow(dem_index_model.name,
                                            index_version.name,
                                            not (index_version.is_deleted is None),
                                            index_version.is_active or 0,
                                            num_docs,
                                            index_version.tag)
                    else:
                        row = EsListRow(dem_index.get_base_name(), "", False, False, 0, "Current (not created)")
                    if row:
                        rows.append(row)
            except AttributeError:
                raise FirstMigrationNotRunError()

            table.header(["Index Base Name", "Index Version Name", "Created", "Active", "Docs", "Tag"])
            table.set_cols_width([20, 35, 7, 6, 5, 9])
            # sort the rows so it's a consistent ordering; these are tuples so they sort nicely
            [table.add_row(r) for r in sorted(rows)]

        log.info(table.draw())
        log.info(
            "An index version name is: \n"
            "{environment prefix}{index name}-{version primary key id}. \n"
            "Most Django Elastic Migrations management commands take the \n"
            "base name (in which case the activated version is used) or \n"
            "the specific index version name."
        )
