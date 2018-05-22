import logging
from django.core.management import CommandError

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.log import get_logger


logger = get_logger()


class Command(ESCommand):
    help = "django-elastic-migrations: drop indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)
        parser.add_argument(
            '--es-only', action='store_true',
            help="Only drop indexes in elasticsearch (!) "
                 "(probably not what you want, just useful for debugging)"
        )
        parser.add_argument(
            '--force', action='store_true',
            help="Drop indexes without having to specify the index version "
        )
        parser.add_argument(
            '--just-prefix', nargs='?',
            help=("Only drop index versions whose name begins with "
                  "the given environment prefix")
        )

    def handle(self, *args, **options):
        indexes, use_version_mode, apply_all = self.get_index_specifying_options(
            options, require_one_include_list=['es_only'])
        es_only = options.get('es_only', False)
        force = options.get('force', False)
        just_prefix = options.get('just-prefix', None)

        if es_only:
            count = 0
            for index_name in indexes:
                logger.warning("Dropping index {} from Elasticsearch only".format(index_name))
                DEMIndexManager.delete_es_created_index(index_name, ignore=[400, 404])
                count += 1
            logger.info("Completed dropping {} indexes from Elasticsearch only".format(count))
        elif apply_all:
            DEMIndexManager.drop_index(
                'all',
                use_version_mode=use_version_mode,
                force=force,
                just_prefix=just_prefix
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.drop_index(
                    index_name,
                    use_version_mode=use_version_mode,
                    force=force,
                    just_prefix=just_prefix
                )
