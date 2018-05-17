from texttable import Texttable

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: list available indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_versions=False)
        parser.add_argument(
            '--es-only', action='store_true',
            help="Only list indexes in elasticsearch, without respect to the models."
        )

    def handle(self, *args, **options):
        print("Available Index Definitions:")

        indexes, _, apply_all = self.get_index_specifying_options(
            options, require_one_include_list=['es_only'])

        es_only = options.get('es_only', False)

        table = Texttable()
        if es_only:
            table.add_row([
                "Name", "Count" ])

            es_indexes = DEMIndexManager.list_es_created_indexes()
            for index in es_indexes:
                count = DEMIndexManager.get_es_index_doc_count(index)
                table.add_row([
                    index,
                    count
                ])

        else:

            table.add_row([
                "Name", "Created", "Is Active", "Num Docs", "Codebase Version"])

            indexes = DEMIndexManager.get_indexes()

            if indexes and not apply_all:
                new_indexes = []
                for index in indexes:
                    if index.get_base_name() in options['index']:
                        new_indexes.append(index)
                indexes = new_indexes

            for dem_index in indexes:
                dem_index_model = dem_index.get_index_model()
                index_versions = dem_index_model.get_available_versions()
                if not index_versions:
                    table.add_row([
                        dem_index.get_base_name(),
                        False,
                        False,
                        dem_index.get_num_docs(),
                        "Current (not created)"])
                else:
                    for indx in index_versions:
                        table.add_row([
                            indx.name,
                            not (indx.is_deleted is None),
                            indx.is_active,
                            dem_index.get_num_docs(),
                            indx.tag])

        print table.draw()
