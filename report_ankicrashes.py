import os, sys, logging
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

from google.appengine.dist import use_library
use_library('django', '1.1')
# Force Django to reload its settings.
from django.conf import settings
settings._target = None

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

from receive_ankicrashes import CrashReport
from receive_ankicrashes import HospitalizedReport
from receive_ankicrashes import Bug

# Remove the standard version of Django
#for k in [k for k in sys.modules if k.startswith('django')]:
#    del sys.modules[k] 
webapp.template.register_template_library('templatetags.basic_math')

class MainPage(webapp.RequestHandler):
	def get(self):
		self.response.headers['Content-type'] = 'text/plain'
		self.response.out.write('Hello world!')

class ReportBugs(webapp.RequestHandler):
	def get(self):
		bugs_query = Bug.all()
		page = int(self.request.get('page', 0))

		bugs = []
		bugs_query.order("-count")
		total_results = bugs_query.count(1000000)
		last_page = max((total_results - 1) // 20, 0)

		if page > last_page:
			page = last_page
		bugs = bugs_query.fetch(20, int(page)*20)
		template_values = {'bugs_list': bugs,
				'total_results': total_results,
				'page_size': 20,
				'page': page,
				'last_page': last_page}

		path = os.path.join(os.path.dirname(__file__), 'templates/bug_list.html')
		self.response.out.write(template.render(path, template_values))



class ReportCrashes(webapp.RequestHandler):
	def get(self):
		hospital_query = HospitalizedReport.all()
		hospitalized = hospital_query.count()

		crashes_query = CrashReport.all()
		bugId = self.request.get('bug_id')
		page = int(self.request.get('page', 0))

		crashes = []
		if bugId:
			bug = Bug.get_by_id(long(bugId))
			crashes_query.filter("bugKey =", bug)
		crashes_query.order("-crashTime")
		total_results = crashes_query.count(1000000)
		last_page = max((total_results - 1) // 20, 0)

		if page > last_page:
			page = last_page
		crashes = crashes_query.fetch(20, int(page)*20)
		template_values = {'crashes_list': crashes,
				'total_results': total_results,
				'page_size': 20,
				'page': page,
				'last_page': last_page,
				'bug_id': bugId,
				'hospitalized': hospitalized}

		path = os.path.join(os.path.dirname(__file__), 'templates/crash_list.html')
		self.response.out.write(template.render(path, template_values))


application = webapp.WSGIApplication(
		[(r'^/ankidroid_triage/?$', MainPage),
			(r'^/ankidroid_triage/report_crashes/?.*', ReportCrashes),
			(r'^/ankidroid_triage/report_bugs/?.*', ReportBugs),
			(r'^/ankidroid_triage/view_crash/?.*', MainPage),
			(r'^/ankidroid_triage/view_bug/?.*', MainPage),
			(r'^/ankidroid_triage/hospital/?.*', MainPage)],
		debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()

