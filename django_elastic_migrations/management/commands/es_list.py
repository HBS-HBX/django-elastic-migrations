from django.core.management import BaseCommand

from django_elastic_migrations import ESIndexManager

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
        print("Available ESSearchIndex Definitions:")

        table = Texttable()
        table.add_row(["Index Name", "Schema Number", "Created", "Activated"])
        for index in ESIndexManager.list_indexes():
            row = [index.get_index_name()]
            model = index.model
            if model:
                row += [model.id, True, model.is_active]
            else:
                row += [1, False, False]
            table.add_row(row)

        print table.draw()