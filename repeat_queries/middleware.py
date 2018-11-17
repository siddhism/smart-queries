from django.utils.deprecation import MiddlewareMixin

from repeat_queries.recorder import SqlRecorder


class DuplicateQueryMiddleware(MiddlewareMixin):
    """
    Middleware to catch duplicate sql queries
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.recorder = SqlRecorder()

    def process_request(self, request):
        if 'admin' in request.path:
            return
        self.recorder.enable_instrumentation()
        self.recorder.record_request(request)
        pass

    def process_response(self, request, response):
        if 'admin' in request.path:
            return response
        self.recorder.disable_instrumentation()
        self.recorder.generate_stats(request, response)
        return response

    def process_template_response(self, request, response):
        if 'admin' in request.path:
            return response
        self.recorder.disable_instrumentation()
        self.recorder.generate_stats(request, response)
        return response
