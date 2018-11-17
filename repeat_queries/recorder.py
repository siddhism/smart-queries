from time import time
import json
import datetime
from pprint import saferepr
from django.db import connections
from django.utils import six
from django.utils.encoding import force_text
SQL_WARNING_THRESHOLD = 1200


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
            # if dt_settings.get_config()['ENABLE_STACKTRACES']:
            #     stacktrace = tidy_stacktrace(reversed(get_stack()))
            # else:
            #     stacktrace = []
            # _params = ''
            try:
                _params = json.dumps([self._decode(p) for p in params])
            except TypeError:
                pass  # object not JSON serializable

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
                'params': _params,
                'raw_params': params,
                # 'stacktrace': stacktrace,
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
            # Per the DB API cursor() does not accept any arguments. There's
            # some code in the wild which does not follow that convention,
            # so we pass on the arguments even though it's not clean.
            # See:
            # https://github.com/jazzband/django-debug-toolbar/pull/615
            # https://github.com/jazzband/django-debug-toolbar/pull/896
            return NormalCursorWrapper(connection.custom_cursor(*args, **kwargs), connection, logger)

        connection.cursor = cursor
        return cursor

    # cursor = connection.cursor
    # connection.cursor = NormalCursorWrapper(cursor, connection, logger)
    # return connection.cursor


def unwrap_cursor(connection, logger):
    pass
    # cursor = connection.cursor
    # connection.cursor = NormalCursorWrapper(cursor, connection, logger)


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

    def enable_instrumentation(self):
        # This is thread-safe because database connections are thread-local.
        for connection in connections.all():
            wrap_cursor(connection, self)

    def disable_instrumentation(self):
        for connection in connections.all():
            unwrap_cursor(connection, self)

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
            # width_ratio_tally = 0
            # factor = int(256.0 / (len(self._databases) * 2.5))
            # for n, db in enumerate(self._databases.values()):
            #     rgb = [0, 0, 0]
            #     color = n % 3
            #     rgb[color] = 256 - n // 3 * factor
            #     nn = color
            #     # XXX: pretty sure this is horrible after so many aliases
            #     while rgb[color] < factor:
            #         nc = min(256 - rgb[color], 256)
            #         rgb[color] += nc
            #         nn += 1
            #         if nn > 2:
            #             nn = 0
            #         rgb[nn] = nc
            #     db['rgb_color'] = rgb

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

                # query['alias'] = alias
                # if 'iso_level' in query:
                #     query['iso_level'] = get_isolation_level_display(query['vendor'],
                #                                                      query['iso_level'])
                # if 'trans_status' in query:
                #     query['trans_status'] = get_transaction_status_display(query['vendor'],
                #                                                            query['trans_status'])

                # query['form'] = SQLSelectForm(auto_id=None, initial=copy(query))

                # if query['sql']:
                #     query['sql'] = reformat_sql(query['sql'])
                # query['rgb_color'] = self._databases[alias]['rgb_color']
                # try:
                #     query['width_ratio'] = (query['duration'] / self._sql_time) * 100
                #     query['width_ratio_relative'] = (
                #         100.0 * query['width_ratio'] / (100.0 - width_ratio_tally))
                # except ZeroDivisionError:
                #     query['width_ratio'] = 0
                #     query['width_ratio_relative'] = 0
                # query['start_offset'] = width_ratio_tally
                # query['end_offset'] = query['width_ratio'] + query['start_offset']
                # width_ratio_tally += query['width_ratio']
                # query['stacktrace'] = render_stacktrace(query['stacktrace'])
                # i += 1

                # query['trace_color'] = trace_colors[query['stacktrace']]

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
        # self.record_stats({
        #     'databases': sorted(self._databases.items(), key=lambda x: -x[1]['time_spent']),
        #     'queries': [q for a, q in self._queries],
        #     'sql_time': self._sql_time,
        # })
