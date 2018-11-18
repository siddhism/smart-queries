from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone

from repeat_queries.recorder import SqlRecorder


def should_record(request):
    # Do not record admin and dashboard urls
    if 'admin' in request.path:
        return False
    if 'dashboard' in request.path:
        return False
    return True


class DuplicateQueryMiddleware(MiddlewareMixin):
    """
    Middleware to catch duplicate sql queries
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.recorder = SqlRecorder()

    def process_request(self, request):
        self.recorder = SqlRecorder()
        if not should_record(request):
            return
        self.recorder.enable_instrumentation()
        self.recorder.record_request(request)
        pass

    def process_response(self, request, response):
        if not should_record(request):
            return response
        self.recorder.disable_instrumentation()
        self.recorder.generate_stats(request, response)
        self.recorder.record_request_end(request)
        return response

    def process_template_response(self, request, response):
        if not should_record(request):
            return response
        self.recorder.disable_instrumentation()
        self.recorder.record_request_end(request)
        return response
