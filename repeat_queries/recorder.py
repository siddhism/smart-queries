from __future__ import absolute_import, unicode_literals

import uuid
import sys
import datetime
from collections import defaultdict
from copy import copy
from threading import local
from pprint import saferepr
from time import time

from django.conf.urls import url
from django.db import connections
from django.utils.translation import ugettext_lazy as _, ungettext_lazy as __

from debug_toolbar.panels import Panel
from debug_toolbar.panels.sql import views
from django.utils.encoding import force_text
from debug_toolbar.panels.sql.forms import SQLSelectForm
from debug_toolbar.panels.sql.utils import (
    contrasting_color_generator, reformat_sql,
)
from debug_toolbar.utils import render_stacktrace


class SQLQueryTriggered(Exception):
    """Thrown when template panel triggers a query"""
    pass


class ThreadLocalState(local):
    def __init__(self):
        self.enabled = True

    @property
    def Wrapper(self):
        if self.enabled:
            return NormalCursorWrapper
        return ExceptionCursorWrapper

    def recording(self, v):
        self.enabled = v


state = ThreadLocalState()
recording = state.recording  # export function


def wrap_cursor(connection, recorder):
    if not hasattr(connection, '_djdt_cursor'):
        connection._djdt_cursor = connection.cursor

        def cursor(*args, **kwargs):
            return state.Wrapper(connection._djdt_cursor(*args, **kwargs), connection, panel)

        connection.cursor = cursor
        return cursor


def unwrap_cursor(connection):
    if hasattr(connection, '_djdt_cursor'):
        del connection._djdt_cursor
        del connection.cursor


class SqlRecorder(object):
    def __init__(self, *args, **kwargs):
        super(SqlRecorder, self).__init__(*args, **kwargs)
        self._offset = {k: len(connections[k].queries) for k in connections}
        self._sql_time = 0
        self._num_queries = 0
        self._queries = []
        self._databases = {}
        self._transaction_status = {}
        self._transaction_ids = {}

    def generate_states(request, response):
        pass
        import ipdb; ipdb.set_trace()

    def enable_instrumentation(self):
        # This is thread-safe because database connections are thread-local.
        for connection in connections.all():
            wrap_cursor(connection, self)

    def disable_instrumentation(self):
        for connection in connections.all():
            unwrap_cursor(connection)


class NormalCursorWrapper(object):
    """
    Wraps a cursor and logs queries.
    """

    def __init__(self, cursor, db, logger):
        self.cursor = cursor
        # Instance of a BaseDatabaseWrapper subclass
        self.db = db
        # logger must implement a ``record`` method
        self.logger = logger

    def _quote_expr(self, element):
        if isinstance(element, six.string_types):
            return "'%s'" % force_text(element).replace("'", "''")
        else:
            return repr(element)

    def _quote_params(self, params):
        if not params:
            return params
        if isinstance(params, dict):
            return {key: self._quote_expr(value) for key, value in params.items()}
        return [self._quote_expr(p) for p in params]

    def _decode(self, param):
        # If a sequence type, decode each element separately
        if isinstance(param, list) or isinstance(param, tuple):
            return [self._decode(element) for element in param]

        # If a dictionary type, decode each value separately
        if isinstance(param, dict):
            return {key: self._decode(value) for key, value in param.items()}

        # make sure datetime, date and time are converted to string by force_text
        CONVERT_TYPES = (datetime.datetime, datetime.date, datetime.time)
        try:
            return force_text(param, strings_only=not isinstance(param, CONVERT_TYPES))
        except UnicodeDecodeError:
            return '(encoded string)'

    def _record(self, method, sql, params):
        start_time = time()
        try:
            return method(sql, params)
        finally:
            stop_time = time()
            duration = (stop_time - start_time) * 1000
            stacktrace = tidy_stacktrace(reversed(get_stack()))
            _params = ''
            try:
                _params = json.dumps([self._decode(p) for p in params])
            except TypeError:
                pass  # object not JSON serializable

            template_info = get_template_info()

            alias = getattr(self.db, 'alias', 'default')
            conn = self.db.connection
            vendor = getattr(conn, 'vendor', 'unknown')

            params = {
                'vendor': vendor,
                'alias': alias,
                'sql': self.db.ops.last_executed_query(
                    self.cursor, sql, self._quote_params(params)),
                'duration': duration,
                'raw_sql': sql,
                'params': _params,
                'raw_params': params,
                'stacktrace': stacktrace,
                'start_time': start_time,
                'stop_time': stop_time,
                'is_slow': duration > 500,
                'is_select': sql.lower().strip().startswith('select'),
                'template_info': template_info,
            }

            if vendor == 'postgresql':
                # If an erroneous query was ran on the connection, it might
                # be in a state where checking isolation_level raises an
                # exception.
                try:
                    iso_level = conn.isolation_level
                except conn.InternalError:
                    iso_level = 'unknown'
                params.update({
                    'trans_id': self.logger.get_transaction_id(alias),
                    'trans_status': conn.get_transaction_status(),
                    'iso_level': iso_level,
                    'encoding': conn.encoding,
                })

            # We keep `sql` to maintain backwards compatibility
            self.logger.record(**params)

    def callproc(self, procname, params=None):
        return self._record(self.cursor.callproc, procname, params)

    def execute(self, sql, params=None):
        return self._record(self.cursor.execute, sql, params)

    def executemany(self, sql, param_list):
        return self._record(self.cursor.executemany, sql, param_list)

    def __getattr__(self, attr):
        return getattr(self.cursor, attr)

    def __iter__(self):
        return iter(self.cursor)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class ExceptionCursorWrapper(object):
    """
    Wraps a cursor and raises an exception on any operation.
    Used in Templates panel.
    """
    def __init__(self, cursor, db, logger):
        pass

    def __getattr__(self, attr):
        raise SQLQueryTriggered()

# TODO
# def omit_path(path):
#     return any(path.startswith(hidden_path) for hidden_path in hidden_paths)


def tidy_stacktrace(stack):
    """
    Clean up stacktrace and remove all entries that:
    1. Are part of Django (except contrib apps)
    2. Are part of socketserver (used by Django's dev server)
    3. Are the last entry (which is part of our stacktracing code)

    ``stack`` should be a list of frame tuples from ``inspect.stack()``
    """
    trace = []
    for frame, path, line_no, func_name, text in (f[:5] for f in stack):
        # if omit_path(os.path.realpath(path)):
        #     continue
        text = (''.join(force_text(t) for t in text)).strip() if text else ''
        trace.append((path, line_no, func_name, text))
    return trace


def get_template_info():
    template_info = None
    cur_frame = sys._getframe().f_back
    try:
        while cur_frame is not None:
            in_utils_module = cur_frame.f_code.co_filename.endswith(
                "/debug_toolbar/utils.py"
            )
            is_get_template_context = (
                cur_frame.f_code.co_name == get_template_context.__name__
            )
            if in_utils_module and is_get_template_context:
                # If the method in the stack trace is this one
                # then break from the loop as it's being check recursively.
                break
            elif cur_frame.f_code.co_name == 'render':
                node = cur_frame.f_locals['self']
                context = cur_frame.f_locals['context']
                if isinstance(node, Node):
                    template_info = get_template_context(node, context)
                    break
            cur_frame = cur_frame.f_back
    except Exception:
        pass
    del cur_frame
    return template_info
