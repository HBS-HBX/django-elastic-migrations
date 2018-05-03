import json

import hashlib
from django.conf import settings
from elasticsearch_dsl import connections

DEFAULT_ES_CLIENT = connections.create_connection()


def get_index_hash_and_json(index):
    spec = index.to_dict()
    json_str = json.dumps(spec)
    hash = hashlib.md5()
    hash.update(json_str)
    return hash.hexdigest(), json_str

