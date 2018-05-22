
from django.core.management import BaseCommand, call_command, CommandError

from django_elastic_migrations.utils.log import get_logger


logger = get_logger()


commands = {
    'list': 'List indexes; calls es_list',
    'create': 'Create indexes; calls es_create',
    'activate': 'Activate indexes; calls es_activate',
    'update': 'Update indexes; calls es_update',
    'deactivate': 'Deactivate indexes; calls es_drop',
    'clear': 'Clears indexes; calls es_clear',
    'drop': 'Drop indexes; calls es_drop',
    'dangerous_reset': 'Dangerously drops all indexes and recreates all indexes (!)'
}


class Command(BaseCommand):
    help = "django-elastic-migrations: base command for search index management"

    def add_arguments(self, parser):
        for cmd, help in commands.items():
            parser.add_argument(
                "--{}".format(cmd), action="store_true", help=help)

    def handle(self, *args, **options):
        for cmd in commands.keys():
            if cmd in options:
                return call_command("es_{}".format(cmd), *args, **options)

    """
    Methods To Specify Indexes
    The methods below are added as an aid to subcommands
    so indexes or index versions are specified in a unified way.
    """

    @classmethod
    def get_index_specifying_help_messages(cls):
        """
        Override in subclasses to customise the messages as necessary
        """
        return {
            "index": (
                "Depending on mode, the name of index(es) "
                "to operate on. By default, the active version will be acted upon."
                "If `--version` is supplied, the specificied versions will be acted upon."
            ),
            "version": (
                "The index names you supply should be considered specific "
                "index version names, including environment prefix."),
            "all": (
                'Operate on all of the active indexes or index versions.'
            )
        }

    @classmethod
    def get_index_version_specifying_arguments(cls, parser):
        messages = cls.get_index_specifying_help_messages()
        parser.add_argument(
            "--version",
            help=messages.get("version"), action="store_true", default=False
        )

    @classmethod
    def get_index_specifying_arguments(cls, parser, include_versions=True, default_all=False):
        messages = cls.get_index_specifying_help_messages()
        parser.add_argument(
            'index', nargs='*',
            help=messages.get("index")
        )

        if include_versions:
            # some arguments do not allow specifying index versions,
            # such as es_create. In that case, do not include this arg.
            cls.get_index_version_specifying_arguments(parser)

        parser.add_argument(
            "--all", action='store_true', default=default_all,
            help=messages.get("all")
        )

    @classmethod
    def get_index_specifying_options(cls, options, require_one_include_list=None):
        use_version_mode = options.get('version', False)
        at_least_one_required = ['index', 'all']

        if require_one_include_list:
            at_least_one_required.extend(require_one_include_list)

        at_least_one = None
        for opt in at_least_one_required:
            if options.get(opt, None):
                at_least_one = True

        if not at_least_one:
            raise CommandError(
                "At least one of {} must be specified".format(
                    ", ".join(at_least_one_required)
                ))

        indexes = options.get('index', [])
        apply_all = options.get('all', False)

        if apply_all and indexes:
            logger.warning(
                "Received --all along with index names: '{indexes}'."
                "Noramlly you would not specify names of indexes "
                "with --all, since --all covers all the indexes. "
                "The --all has been canceled; operating on just '{indexes}'."
                "To clear *all* the indexes, just use --all.".format(
                    indexes=", ".join(indexes))
            )
            apply_all = False

        return indexes, use_version_mode, apply_all


ESCommand = Command
