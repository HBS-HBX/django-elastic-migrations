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
        print("Available DEMIndex Definitions:")

        table = Texttable()
        table.add_row(["Index Name", "Schema Number", "Created", "Activated"])
        for dem_index in DEMIndexManager.get_indexes():
            row = [dem_index.get_index_base_name()]
            dem_index_model = dem_index.get_index_model()
            index_versions = dem_index_model.indexversion_set.all()
            if not index_versions:
                row += [1, False, False]
                table.add_row(row)
            else:
                for indx in index_versions:
                    row += [indx.id, True, indx.is_active]
                    table.add_row(row)

        print table.draw()
