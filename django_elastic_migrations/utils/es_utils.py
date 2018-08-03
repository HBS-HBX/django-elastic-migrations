from __future__ import print_function
import hashlib
import json


def get_index_hash_and_json(index):
    spec = index.to_dict()
    # note - need to add .encode('utf-8') for py3
    json_str = json.dumps(spec, sort_keys=True)
    md5_hash = hashlib.md5()
    md5_hash.update(json_str)
    return md5_hash.hexdigest(), json_str
