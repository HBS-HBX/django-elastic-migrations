from __future__ import print_function
import hashlib
import json


def get_index_hash_and_json(index):
    spec = index.to_dict()
    json_str = json.dumps(spec)
    hash = hashlib.md5()
    hash.update(json_str)
    return hash.hexdigest(), json_str
