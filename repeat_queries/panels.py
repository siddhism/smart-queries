from debug_toolbar.panels import DebugPanel
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _


class RepeatQueryPanel(DebugPanel):
    name = 'Repeat Query'
    has_content = True

    def nav_title(self):
        return _('Useful Infos')

    def title(self):
        return _('My Useful Debug Panel')

    def url(self):
        return ''

    def content(self):
        context = self.context.copy()
        context.update({
            'infos': [
                {'plop': 'plip'},
                {'plop': 'plup'},
            ],
        })
        return render_to_string('panels/repeat_query_panel.html', context)
