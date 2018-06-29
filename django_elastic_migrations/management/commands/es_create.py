from __future__ import print_function

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: create an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_exact=False)
        parser.add_argument(
            '--force', action='store_true',
            help='create a new index version even if the schema has not changed'
        )

    def handle(self, *args, **options):
        indexes, _, apply_all, _, _ = self.get_index_specifying_options(options)
        force = options.get('force')

        if apply_all:
            DEMIndexManager.create_index(
                'all',
                force=force,
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.create_index(
                    index_name,
                    force=force
                )

