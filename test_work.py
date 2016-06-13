import requests


class MyInt(object):
    def __new__(cls, *args, **kwargs):
        return 12


class TestObject(object):
    _x = 10
    protection = True

    def __init__(self):
        self.__class__.x = property(lambda self: self._x)

    def __getitem__(self, item):
        return "I'm a dict"

    def add_setter(self):
        self.__class__.x = property(lambda self: self._x,
                                    lambda self, v: setattr(self, '_x', v))

    def fetch_github_status(self, url='https://status.github.com/api/status.json'):
        return str(requests.get(url).json()['status'])


def main():
    """
    >>> myint = MyInt()
    >>> myint
    12
    >>> type(myint) == int
    True
    >>> to = TestObject()
    >>> # output "Creating class"
    >>> to['key']
    "I'm a dict"
    >>> to.x  # x is a property of TestObject
    10
    >>> to.x = 15
    Traceback (most recent call last):
        ...
    AttributeError: can't set attribute
    >>> to.add_setter()  # this should add setter for property
    >>> to.x = 15
    >>> to.x == 15
    True
    >>> to.fetch_github_status('https://status.github.com/api/status.json')
    'good'
    """

import doctest
doctest.testmod()


import unittest
class TestMain(unittest.TestCase):
    pass

unittest.main()
