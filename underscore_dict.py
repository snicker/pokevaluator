class underscore_dict(dict):
    """
    a dict like object that forces key to be pythonic and follow the underscore
    convention.

    eg::

    >>> d = underscore_dict(dict(myKey='my_value'))
    >>> print d
    'my_key': 'my_value'}

    >>> d['my_key'] = 'my_value_2'
    >>> print d
    {'my_key': 'my_value_2'}

    >>> d.update(myKey='my_value_3')
    >>> print d
    {'my_key': 'my_value_3'}

    >>> del d['my_key']
    >>> print d
    {}

    And this is what happens when java code gets too close to python code.

    """

    def __init__(self, *args, **kwargs):
        self.update(*args, **kwargs)

    def __setitem__(self, key, value):
        # translate java's camelcase name convention to python's
        # underscore convention from:
        # http://github.com/mw44118/pyohio-metaclasses-talk/blob/master/listing1.py#21
        pythonic_key = ''
        for c in key:
            if c.isupper():
                pythonic_key += '_%c' % c.lower()
            else:
                pythonic_key += c

        super(underscore_dict, self).__setitem__(pythonic_key, value)

    def update(self, *args, **kwargs):
         if args:
             if len(args) > 1:
                 raise TypeError("update expected at most 1 arguments, got %d" % len(args))
             other = dict(args[0])
             for key in other:
                 self[key] = other[key]
         for key in kwargs:
             self[key] = kwargs[key]

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]

import json

class JSONUnderscoreDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        return underscore_dict(obj)