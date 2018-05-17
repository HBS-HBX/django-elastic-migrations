from texttable import Texttable

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.exceptions import FirstMigrationNotRunError
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: list available indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_versions=False, default_all=True)
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
                "Name", "Created", "Is Active", "Num Docs", "Created In Tag"])

            indexes = DEMIndexManager.get_indexes()

            if indexes and not apply_all:
                new_indexes = []
                for index in indexes:
                    if index.get_base_name() in options['index']:
                        new_indexes.append(index)
                indexes = new_indexes

            try:
                for dem_index in indexes:
                    dem_index_model = dem_index.get_index_model()
                    index_versions = dem_index_model.get_available_versions()
                    if index_versions:
                        for index in index_versions:
                            table.add_row([
                                index.name,
                                not (index.is_deleted is None),
                                index.is_active or 0,
                                dem_index.get_num_docs(),
                                index.tag])
                    else:
                        table.add_row([
                            dem_index.get_base_name(),
                            False,
                            False,
                            dem_index.get_num_docs(),
                            "Current (not created)"])
            except AttributeError:
                raise FirstMigrationNotRunError()

        print(table.draw())
        print(
            "Reminder: an index version name looks like 'my_index-4', " 
            "and its base index name \n"
            "looks like 'my_index'. Most Django Elastic Migrations management commands \n"
            "take the base name (in which case the activated version is used) \n"
            "or the specific index version name."
        )

