from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.exceptions import CannotDropAllIndexesWithoutForceArg
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger

logger = get_logger()


class Command(ESCommand):
    help = "django-elastic-migrations: drop indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_older=True)
        parser.add_argument(
            '--es-only', action='store_true',
            help=("Drop indexes in elasticsearch "
                  "without updating DEM's IndexVersion ORM model (!)")
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
        indexes, exact_mode, apply_all, older_mode, _ = self.get_index_specifying_options(
            options, require_one_include_list=['es_only'])
        es_only = options.get('es_only', False)
        force = options.get('force', False)
        just_prefix = options.get('just-prefix', None)

        if apply_all:
            if not force:
                raise CannotDropAllIndexesWithoutForceArg(
                    "When using --es-only, cannot use --all without --force"
                )
            DEMIndexManager.drop_index(
                'all',
                exact_mode=exact_mode,
                force=force,
                just_prefix=just_prefix,
                older_mode=older_mode,
                es_only=es_only
            )
            if es_only:
                indexes = DEMIndexManager.list_es_created_indexes()

                count = 0
                for index_name in indexes:
                    if just_prefix and not index_name.startswith(just_prefix):
                        continue
                    logger.warning("Dropping index {} from Elasticsearch only".format(index_name))
                    DEMIndexManager.delete_es_created_index(index_name, ignore=[404])
                    count += 1
                logger.info("Completed dropping {} indexes from Elasticsearch only".format(count))
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.drop_index(
                    index_name,
                    exact_mode=exact_mode,
                    force=force,
                    just_prefix=just_prefix,
                    older_mode=older_mode,
                    es_only=es_only
                )
