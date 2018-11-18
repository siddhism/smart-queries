from time import time
import json
import datetime
from pprint import saferepr
from django.db import connections
from django.utils import six
from django.utils import timezone
from django.utils.encoding import force_text
SQL_WARNING_THRESHOLD = 1200
from repeat_queries.utils import convert_epoch_to_datetime
from repeat_queries.models import Request, SQLQuery


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
            import traceback
            stacktrace = ''.join(reversed(traceback.format_stack()))
            # if dt_settings.get_config()['ENABLE_STACKTRACES']:
                # stacktrace = tidy_stacktrace(reversed(get_stack()))
            # else:
            #     stacktrace = []
            # _params = ''
            # try:
            #     _params = json.dumps([self._decode(p) for p in params])
            # except TypeError:
            #     pass  # object not JSON serializable

            # template_info = get_template_info()

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
                # 'params': _params,
                'raw_params': params,
                'stacktrace': stacktrace,
                'start_time': start_time,
                'stop_time': stop_time,
                # 'is_slow': duration > dt_settings.get_config()['SQL_WARNING_THRESHOLD'],
                'is_select': sql.lower().strip().startswith('select'),
                # 'template_info': template_info,
            }
            print ('From inside the custom cursor record')
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


def wrap_cursor(connection, logger):
    if not hasattr(connection, 'custom_cursor'):
        connection.custom_cursor = connection.cursor

        def cursor(*args, **kwargs):
            return NormalCursorWrapper(connection.custom_cursor(*args, **kwargs), connection, logger)

        connection.cursor = cursor
        return cursor


def unwrap_cursor(connection, logger):
    if hasattr(connection, 'custom_cursor'):
        del connection.custom_cursor
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
        self.request = None

    def enable_instrumentation(self):
        # This is thread-safe because database connections are thread-local.
        for connection in connections.all():
            wrap_cursor(connection, self)

    def disable_instrumentation(self):
        for connection in connections.all():
            unwrap_cursor(connection, self)

    def record_request(self, request):
        # When we start a request, let's create request object
        self.profile = {
            # 'func_name': func_name,
            # 'name': self.name,
            'path': request.path,
            'body': request.body,
            'method': request.method,
            'start_time': timezone.now()
            # 'request': DataCollector().request
            # 'line_num': line_num,
            # 'dynamic': self._dynamic,
        }
        request = Request.objects.create(**self.profile)
        self.request = request

    def record(self, alias, **kwargs):
        self._queries.append((alias, kwargs))
        if alias not in self._databases:
            self._databases[alias] = {
                'time_spent': kwargs['duration'],
                'num_queries': 1,
            }
        else:
            self._databases[alias]['time_spent'] += kwargs['duration']
            self._databases[alias]['num_queries'] += 1
        self._sql_time += kwargs['duration']
        self._num_queries += 1

    def generate_stats(self, request, response):
        from collections import defaultdict
        query_similar = defaultdict(lambda: defaultdict(int))
        query_duplicates = defaultdict(lambda: defaultdict(int))

        # The keys used to determine similar and duplicate queries.
        def similar_key(query):
            return query['raw_sql']

        def duplicate_key(query):
            raw_params = () if query['raw_params'] is None else tuple(query['raw_params'])
            # saferepr() avoids problems because of unhashable types
            # (e.g. lists) when used as dictionary keys.
            # https://github.com/jazzband/django-debug-toolbar/issues/1091
            return (query['raw_sql'], saferepr(raw_params))

        if self._queries:

            trans_ids = {}
            trans_id = None
            i = 0
            for alias, query in self._queries:
                query_similar[alias][similar_key(query)] += 1
                query_duplicates[alias][duplicate_key(query)] += 1

                trans_id = query.get('trans_id')
                last_trans_id = trans_ids.get(alias)

                if trans_id != last_trans_id:
                    if last_trans_id:
                        self._queries[(i - 1)][1]['ends_trans'] = True
                    trans_ids[alias] = trans_id
                    if trans_id:
                        query['starts_trans'] = True
                if trans_id:
                    query['in_trans'] = True

            if trans_id:
                self._queries[(i - 1)][1]['ends_trans'] = True

        # Queries are similar / duplicates only if there's as least 2 of them.
        # Also, to hide queries, we need to give all the duplicate groups an id
        # query_colors = contrasting_color_generator()
        query_colors = ['red', 'blue']
        query_similar_colors = {
            alias: {
                query: (similar_count, 'blue')
                for query, similar_count in queries.items()
                if similar_count >= 2
            }
            for alias, queries in query_similar.items()
        }
        query_duplicates_colors = {
            alias: {
                query: (duplicate_count, 'blue')
                for query, duplicate_count in queries.items()
                if duplicate_count >= 2
            }
            for alias, queries in query_duplicates.items()
        }

        for alias, query in self._queries:
            try:
                (query["similar_count"], query["similar_color"]) = (
                    query_similar_colors[alias][similar_key(query)]
                )
                (query["duplicate_count"], query["duplicate_color"]) = (
                    query_duplicates_colors[alias][duplicate_key(query)]
                )
            except KeyError:
                pass

        for alias, alias_info in self._databases.items():
            try:
                # TODO : that's what we want
                alias_info["similar_count"] = sum(
                    e[0] for e in query_similar_colors[alias].values()
                )
                alias_info["duplicate_count"] = sum(
                    e[0] for e in query_duplicates_colors[alias].values()
                )
            except KeyError:
                pass
        print ('Inside stats recorder generate stats')
        print (self._queries)
        for alias, query in self._queries:
            k = {
                'query': query['raw_sql'],
                'duration': query['duration'],
                'start_time': convert_epoch_to_datetime(query['start_time']),
                'stop_time': convert_epoch_to_datetime(query['stop_time']),
                'duplicate_count': query.get('duplicate_count'),
                'similar_count': query.get('similar_count'),
                'request': self.request,
                'traceback': query.get('stacktrace')
            }
            sql_query = SQLQuery(**k)
            sql_query.save()
            print (sql_query)

        # self.record_stats({
        #     'databases': sorted(self._databases.items(), key=lambda x: -x[1]['time_spent']),
        #     'queries': [q for a, q in self._queries],
        #     'sql_time': self._sql_time,
        # })
