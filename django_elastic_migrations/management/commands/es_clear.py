import logging
from django.core.management import CommandError

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: clear documents from elasticsearch indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)

    def handle(self, *args, **options):
        indexes, use_version_mode, apply_all = self.get_index_specifying_options(options)

        if apply_all:
            DEMIndexManager.clear_index(
                'all',
                use_version_mode=use_version_mode,
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.clear_index(
                    index_name,
                    use_version_mode=use_version_mode
                )
