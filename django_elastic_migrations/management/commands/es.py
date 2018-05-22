
from django.core.management import BaseCommand, call_command, CommandError

from django_elastic_migrations.utils.log import getLogger


logger = getLogger()


commands = {
    'list': 'List indexes; calls es_list',
    'create': 'Create indexes; calls es_create',
    'activate': 'Create indexes; calls es_activate',
    'update': 'Create indexes; calls es_update',
    'drop': 'Create indexes; calls es_drop',
    'dangerous_reset': 'Dangerously drops all indexes and recreates all indexes (!)'
}


class Command(BaseCommand):
    help = "django-elastic-migrations: base command for search index management"

    MODE_INDEXES = 'index'
    MODE_VERSIONS = 'version'

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

    def get_index_specifying_help_messages(self):
        """
        Override in subclasses to customise the messages as necessary
        """
        return {
            "mode": "Specify whether to operate on indexes or index versions",
            "index": (
                "Depending on --mode, the name of index(es) or index version(s) "
                "to operate on. In the case of `--mode {mode_indexes}` (the default), "
                "the active version will be operated upon, and indexes without an "
                "active version will be ignored.".format(mode_indexes=self.MODE_INDEXES)
            ),
            "all": (
                'Operate on all of the active indexes or index versions, depending on '
                'whether `--mode {mode_index}`, or `--mode {mode_version}` is '
                'supplied.'.format(mode_index=self.MODE_INDEXES, mode_version=self.MODE_VERSIONS)
            )
        }

    def get_index_version_specifying_arguments(self, parser):
        messages = self.get_index_specifying_help_messages()
        parser.add_argument(
            "--mode",
            help=messages.get("mode"),
            choices=[self.MODE_INDEXES, self.MODE_VERSIONS],
            default=self.MODE_INDEXES
        )

    def get_index_specifying_arguments(self, parser, include_versions=True, default_all=False):
        messages = self.get_index_specifying_help_messages()
        parser.add_argument(
            'index', nargs='*',
            help=messages.get("index")
        )

        if include_versions:
            # some arguments do not allow specifying index versions,
            # such as es_create. In that case, do not include this arg.
            self.get_index_version_specifying_arguments(parser)

        parser.add_argument(
            "--all", action='store_true', default=default_all,
            help=messages.get("all")
        )

    def get_index_specifying_options(self, options, require_one_include_list=None):
        mode = options.get('mode', self.MODE_INDEXES)
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
        use_version_mode = mode == self.MODE_VERSIONS
        apply_all = options.get('all', False)

        if apply_all:
            if indexes:
                logger.warning(
                    "./manage.py es_clear --all received named indexes "
                    "'{}': these specified index names will be ignored "
                    "because you have requested to clear *all* the "
                    "indexes.".format(", ".join(indexes))
                )

        return indexes, use_version_mode, apply_all


ESCommand = Command
