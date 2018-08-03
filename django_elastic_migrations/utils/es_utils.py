
import hashlib
import json


def get_index_hash_and_json(index):
    spec = index.to_dict()
    json_str = json.dumps(spec, sort_keys=True).encode('utf-8')
    hash = hashlib.md5()
    hash.update(json_str)
    return hash.hexdigest(), json_str
