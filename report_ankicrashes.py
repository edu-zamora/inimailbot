import os
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

from receive_ankicrashes import CrashReport

class MainPage(webapp.RequestHandler):
	def get(self):
		self.response.headers['Content-type'] = 'text/plain'
		self.response.out.write('Hello world!')

class ReportCrashes(webapp.RequestHandler):
	def get(self):
		#self.response.headers['Content-type'] = 'text/html'
		crashes_query = CrashReport.all()
		crashes = crashes_query.fetch(6)

		template_values = { 'crashes_list': crashes }
		path = os.path.join(os.path.dirname(__file__), 'templates/crash_list.html')
		self.response.out.write(template.render(path, template_values))




application = webapp.WSGIApplication(
		[(r'^/ankidroid_triage/?$', MainPage),
			(r'^/ankidroid_triage/report_crashes/?.*', ReportCrashes),
			(r'^/ankidroid_triage/report_bugs/?.*', ReportCrashes),
			(r'^/ankidroid_triage/view_crash/?.*', ReportCrashes),
			(r'^/ankidroid_triage/view_bug/?.*', ReportCrashes),
			(r'^/ankidroid_triage/view_hospital/?.*', ReportCrashes)],
		debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()

