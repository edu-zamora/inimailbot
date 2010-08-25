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
webapp.template.register_template_library('templatetags.basic_math')

class MainPage(webapp.RequestHandler):
	def get(self):
		self.response.headers['Content-type'] = 'text/plain'
		self.response.out.write('Hello world!')

class ViewBug(webapp.RequestHandler):
	issueStatusOrder = {
			'Started': 0,
			'Accepted': 0,
			'New': 0,
			'FixedInDev': 1,
			'Fixed': 2,
			'Done': 2,
			'Invalid': 3,
			'WontFix': 3,
			'Duplicate': 4
			}
	issuePriorityOrder = {
			'Critical': 0,
			'High': 1,
			'Medium': 2,
			'Low': 3
			}

	@classmethod
	def compareIssues(cls, a, b):
		# First prioritize on Status, then on priority, then on -ID
		logging.info("Comparing " + str(a) + " " + str(b))
		logging.info("Comparing status: " + str(cls.issueStatusOrder[a['status']]) + " " + str(cls.issueStatusOrder[b['status']]) + " " + str(cmp(cls.issueStatusOrder[a['status']], cls.issueStatusOrder[b['status']])))
		logging.info("Comparing priority: " + str(cls.issuePriorityOrder[a['priority']]) + " " + str(cls.issuePriorityOrder[b['priority']]) + " " + str(cmp(cls.issuePriorityOrder[a['priority']], cls.issuePriorityOrder[b['priority']])))
		logging.info("Comparing ID: " + str(cmp(-a['id'], -b['id'])))
		return cmp(cls.issueStatusOrder[a['status']], cls.issueStatusOrder[b['status']]) or cmp(cls.issuePriorityOrder[a['priority']], cls.issuePriorityOrder[b['priority']]) or cmp(-a['id'], -b['id'])

	def findIssue(self, signature):
		# format signature for google query
		urlEncodedSignature = quote_plus(signature)
		logging.info("URL-Encoded: '" + urlEncodedSignature + "'")
		url = r"http://code.google.com/p/ankidroid/issues/list?can=1&q=" + urlEncodedSignature + r"&colspec=ID+Status+Priority"
		try:
			result = fetch(url)
			if result.status_code == 200:
				logging.debug("Results retrieved (" + str(len(result.content)) + "): '" + str(result.content) + "'")
				soup = BeautifulSoup(result.content)
				issueID = soup.findAll('td', {'class': 'vt id col_0'})
				issueStatus = soup.findAll('td', {'class': 'vt col_1'})
				issuePriority = soup.findAll('td', {'class': 'vt col_2'})
				logging.debug("Issue found: " + str(issueID) + " " + str(issueStatus) + " " + str(issuePriority))
				issues = []
				for i, issue in enumerate(issueID):
					issues.append({'id': long(issueID[i].a.string), 'status':	strip(issueStatus[i].a.string), 'priority': strip(issuePriority[i].a.string)})
				logging.info("Unsorted list: " + str(issues))
				issues.sort(ViewBug.compareIssues)
				logging.info("Sorted list: " + str(issues))
				return issues
		except Error, e:
			logging.error("Error while retrieving query results: %s" % str(e))
			return []

	def post(self):
		post_args = self.request.arguments()
		bugId = self.request.get('bug_id')
		bug = Bug.get_by_id(long(bugId))
		issues = []
		if bug:
			if "find_issue" in post_args:
				# Scan for matching issue
				issues = self.findIssue(bug.signature)
			elif "save_issue" in post_args:
				# Save the entered issue
				issueName = self.request.get('issue')
				if re.search(r"^[0-9]*$", issueName):
					if issueName:
						bug.issueName = long(issueName)
						bug.linked = False
						bug.fixed = False
					else:
						bug.issueName = None
						bug.linked = True
					bug.put()
					logging.debug("Saving issue - value: '" + issueName + "'")
				else:
					logging.warning("Saving issue - non numeric value: '" + issueName + "'")
		else:
			logging.warning("Saving issue - not valid bug ID: '" + bugId + "'")
		template_values = {'bg': bug, 'issues': issues}
		path = os.path.join(os.path.dirname(__file__), 'templates/bug_view.html')
		self.response.out.write(template.render(path, template_values))

	def get(self):
		bugId = self.request.get('bug_id')
		bug = Bug.get_by_id(long(bugId))
		template_values = {'bg': bug}
		path = os.path.join(os.path.dirname(__file__), 'templates/bug_view.html')
		self.response.out.write(template.render(path, template_values))

class ViewCrash(webapp.RequestHandler):
	def get(self):
		crashId = self.request.get('crash_id')
		crash = CrashReport.get_by_id(long(crashId))
		template_values = {'cr': crash}
		path = os.path.join(os.path.dirname(__file__), 'templates/crash_view.html')
		self.response.out.write(template.render(path, template_values))


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
			(r'^/ankidroid_triage/view_crash/?.*', ViewCrash),
			(r'^/ankidroid_triage/view_bug/?.*', ViewBug),
			(r'^/ankidroid_triage/hospital/?.*', MainPage)],
		debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()

