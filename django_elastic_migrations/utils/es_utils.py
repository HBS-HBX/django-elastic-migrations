import hashlib
import json


def get_index_hash_and_json(index):
    spec = index.to_dict()
    json_str = json.dumps(spec, sort_keys=True)
    return get_hash(json_str), json_str


def get_hash(json_str):
    md5_hash = hashlib.md5()
    md5_hash.update(json_str.encode('utf-8'))
    return md5_hash.hexdigest()
