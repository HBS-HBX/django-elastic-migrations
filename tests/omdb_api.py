from __future__ import (absolute_import, division, print_function, unicode_literals)

import os
from pprint import pprint

import requests
from six import python_2_unicode_compatible

try:
    # py3
    # noinspection PyCompatibility
    from urllib.parse import urlencode as encoder
except ImportError:
    # py2
    from urllib import urlencode as encoder


@python_2_unicode_compatible
class OmdbAPIQuery(object):
    BASE_URL = "http://www.omdbapi.com"
    DEFAULT_API_KEY = 'Get your own from https://www.omdbapi.com/apikey.aspx'

    STATUS_UNREQUESTED = "Unrequested"
    STATUS_SUCCESS = "Successful"
    STATUS_FAILURE = "Failed"

    def __init__(self, title="", api_key=DEFAULT_API_KEY):
        self._qdict = {}
        self._data = {}
        self._req = None
        self.set_title(title)
        self.set_api_key(api_key)

    def __str__(self):
        return "{status} {query_desc}".format(status=self.status, query_desc=self.get_query_description())

    @property
    def status(self):
        if not self._req:
            return self.STATUS_UNREQUESTED
        elif self._req.status_code == 200:
            return self.STATUS_SUCCESS
        else:
            return self.STATUS_FAILURE

    @property
    def unrequested(self):
        return self.status == self.STATUS_UNREQUESTED

    @property
    def successful(self):
        return self.status == self.STATUS_SUCCESS

    def execute(self):
        self._req = requests.get(self.get_query_url())
        if self.status:
            data = self._req.json()
            self._data = self.transform_api_response(data)
            return self._data
        raise ValueError("There was a problem requesting {}: got status code {} and text {}".format(
            self.get_query_url(), self.status_code, self.text))

    def get_data(self):
        if self.unrequested:
            self.execute()
        if self.successful:
            return self._data
        raise ValueError("Query was not successful; status is {}".format(self.status))

    def get_query_description(self):
        return "OMDB API search for '{}'".format(self.title)

    def get_query_url(self):
        querystring = encoder(self._qdict)
        return "{base_url}/?{querystring}".format(base_url=self.BASE_URL, querystring=querystring)

    def print_resuts(self):
        pprint(self.get_data())

    @property
    def title(self):
        return self._qdict.get('t')

    def set_title(self, title):
        if not title:
            raise ValueError("title is required")
        self._qdict.update({'t': title})

    def set_api_key(self, api_key=DEFAULT_API_KEY):
        if api_key == self.DEFAULT_API_KEY:
            api_key = os.environ.get('OMDB_API_KEY', 'Get your own from https://www.omdbapi.com/apikey.aspx')
            if api_key == self.DEFAULT_API_KEY:
                raise ValueError(self.DEFAULT_API_KEY)
        self._qdict.update({'apikey': api_key})

    @classmethod
    def transform_api_response(cls, data):
        newdata = {}
        for key, val in data.items():
            key = key.lower()
            transformer = getattr(cls, "transform_{}".format(key), None)
            if transformer:
                val = transformer(val)
            newdata[key] = val
        return newdata

    @staticmethod
    def transform_runtime(val):
        return int(val.split(" min")[0])
