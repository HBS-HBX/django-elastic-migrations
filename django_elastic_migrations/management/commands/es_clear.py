from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger

logger = get_logger()


class Command(ESCommand):
    help = "django-elastic-migrations: clear documents from elasticsearch indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_older=True)

    def handle(self, *args, **options):
        indexes, exact_mode, apply_all, older_mode, _ = self.get_index_specifying_options(options)

        if apply_all:
            DEMIndexManager.clear_index(
                'all',
                exact_mode=exact_mode,
                older_mode=older_mode
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.clear_index(
                    index_name,
                    exact_mode=exact_mode,
                    older_mode=older_mode
                )
