from django.core.management import BaseCommand

from django_elastic_migrations import DEMIndexManager

from texttable import Texttable

from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: list available indexes"

    def add_arguments(self, parser):
        parser.add_argument(
            'index', nargs='*',
            help='Name of an index'
        )

    def handle(self, *args, **options):
        print("Available Index Definitions:")

        table = Texttable()
        table.add_row(["Name", "Created", "Is Active", "Codebase Version"])

        indexes = DEMIndexManager.get_indexes()

        if options['index']:
            new_indexes = []
            for index in indexes:
                if index.get_base_name() in options['index']:
                    new_indexes.append(index)
            indexes = new_indexes

        for dem_index in indexes:
            dem_index_model = dem_index.get_index_model()
            index_versions = dem_index_model.indexversion_set.all()
            if not index_versions:
                table.add_row([dem_index.get_base_name(), False, False, "Current (not created)"])
            else:
                for indx in index_versions:
                    table.add_row([indx.name, not (indx.is_deleted is None), indx.is_active, indx.tag])

        print table.draw()
