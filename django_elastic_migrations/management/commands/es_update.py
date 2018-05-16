from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: update an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)

    def handle(self, *args, **options):
        indexes, use_version_mode, apply_all = self.get_index_specifying_options(options)

        indexes_to_update = options.get('index', [])
        if indexes_to_update:
            for index_name in indexes_to_update:
                DEMIndexManager.update_index(index_name)
        else:
            DEMIndexManager.update_index(None, all=True)

        # TBD:
        # if apply_all:
        #     DEMIndexManager.update_index(
        #         'all',
        #         use_version_mode=use_version_mode,
        #     )
        # elif indexes:
        #     for index_name in indexes:
        #         DEMIndexManager.update_index(
        #             index_name,
        #             use_version_mode=use_version_mode
        #         )
