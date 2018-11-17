from django.utils.deprecation import MiddlewareMixin

from repeat_queries.recorder import SqlRecorder


class DuplicateQueryMiddleware(MiddlewareMixin):
    """
    Middleware to catch duplicate sql queries
    """
    def __init__(self, *args, **kwargs):
        self.recorder = SqlRecorder()

    def process_request(self, request):
        self.recorder.enable_instrumentation()
        pass

    def process_response(self, request, response):
        self.recorder.generate_states(request, response)
        self.recorder.disable_instrumentation()
        return response
