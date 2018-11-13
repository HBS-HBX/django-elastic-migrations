# encoding: utf-8

from django_elastic_migrations.utils import importlib


def import_module_element(path):
    path_bits = path.split('.')
    # Cut off the class name at the end.
    module_attr = path_bits.pop()
    module_path = '.'.join(path_bits)
    module_itself = importlib.import_module(module_path)

    if not hasattr(module_itself, module_attr):
        raise ImportError("The Python module '%s' has no '%s' attribute." % (module_path, module_attr))

    return getattr(module_itself, module_attr)
