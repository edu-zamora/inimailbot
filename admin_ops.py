import os, sys, logging, re
from urllib import quote_plus
from string import strip
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

from google.appengine.dist import use_library
use_library('django', '1.1')
# Force Django to reload its settings.
from django.conf import settings
settings._target = None

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
from google.appengine.api.urlfetch import fetch
from google.appengine.api.urlfetch import Error

from receive_ankicrashes import CrashReport
from receive_ankicrashes import HospitalizedReport
from receive_ankicrashes import Bug
from BeautifulSoup import BeautifulSoup

# Remove the standard version of Django
#for k in [k for k in sys.modules if k.startswith('django')]:
#    del sys.modules[k] 
#webapp.template.register_template_library('templatetags.basic_math')

class ShowCrashBody(webapp.RequestHandler):
	def get(self):
		crId = long(self.request.get('id'))
		cr = CrashReport.get_by_id(crId)
		m = re.search(r'^(.*--\&gt; END REPORT 1 \&lt;--).*$', cr.report, re.S)
		new_report = m.group(1)
		template_values = {'crash_body': cr.report,
				'new_crash_body': new_report}
		logging.info(cr.report)
		logging.info(new_report)
		path = os.path.join(os.path.dirname(__file__), 'templates/admin_ops_show.html')
		self.response.out.write(template.render(path, template_values))

class AdminOps(webapp.RequestHandler):
	@classmethod
	def getCrashSignature2(cls, body):
		result1 = ''
		result2 = ''
		m1 = re.search(r"Begin Stacktrace\s*(<br>\s*)*(\S.*?\S)\s*<br>", body, re.M)
		if m1 and m1.groups():# and m2 and m2.groups():
			result1 = re.sub(r"\$[a-fA-F0-9@]*", "", m1.group(2))
		m2 = re.search(r"<br>\s*(at\scom\.ichi2\.anki\..*?\S)\s*<br>", body, re.M|re.U)
		if m2 and m2.groups():# and m2 and m2.groups():
			result2 = re.sub(r"\$[a-fA-F0-9@]*", "", m2.group(1))
		return result1 + "-" + result2
	def get(self):

		crashes_query = CrashReport.all()
		crashes = []
		crashes_query.order("crashTime")
		total_results = crashes_query.count(1000000)

		crashes = crashes_query.fetch(200)
		results_list=[]
		for cr in crashes:
			m = re.search(r'^(.*--\&gt; END REPORT \d \&lt;--<br>).*$', cr.report, re.S)
			new_report = ''
			if m:
				new_report = m.group(1)
			else:
				new_report = cr.report
			if cr.report != new_report:
				results_list.append({'id': cr.key().id(), 'sig1': cr.report, 'sig2': new_report})
			#results_list.append({'id': cr.key().id(), 'sig1': CrashReport.getCrashSignature(cr.report), 'sig2': self.getCrashSignature2(cr.report)})
		template_values = {'results_list': results_list}
		path = os.path.join(os.path.dirname(__file__), 'templates/admin_ops.html')
		self.response.out.write(template.render(path, template_values))

application = webapp.WSGIApplication(
		[(r'^/ankidroid_triage/admin_show.*$', ShowCrashBody),
		(r'^/ankidroid_triage/admin_ops$', AdminOps)],
		debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()

