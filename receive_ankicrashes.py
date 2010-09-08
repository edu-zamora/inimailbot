# ###
# Copyright (c) 2010 Konstantinos Spyropoulos <inigo.aldana@gmail.com>
#
# This file is part of inimailbot
#
# inimailbot is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# inimailbot is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with inimailbot.
# If not, see http://www.gnu.org/licenses/.
# #####

import logging, email, re, hashlib
from datetime import datetime
from cgi import escape
from string import strip
from urllib import quote
from urllib import quote_plus
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api.urlfetch import fetch
from google.appengine.api.urlfetch import Error

from pytz.gae import pytz
from pytz import timezone, UnknownTimeZoneError
from BeautifulSoup import BeautifulStoneSoup
from BeautifulSoup import BeautifulSoup

class HospitalizedReport(db.Model):
	email = db.StringProperty(required=True)
	crashId = db.StringProperty(required=True)
	crashBody = db.TextProperty(required=True)
	diagnosis = db.StringProperty()
	processed = db.BooleanProperty()

class Bug(db.Model):
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
		#logging.info("Comparing " + str(a) + " " + str(b))
		#logging.info("Comparing status: " + str(cls.issueStatusOrder[a['status']]) + " " + str(cls.issueStatusOrder[b['status']]) + " " + str(cmp(cls.issueStatusOrder[a['status']], cls.issueStatusOrder[b['status']])))
		#logging.info("Comparing priority: " + str(cls.issuePriorityOrder[a['priority']]) + " " + str(cls.issuePriorityOrder[b['priority']]) + " " + str(cmp(cls.issuePriorityOrder[a['priority']], cls.issuePriorityOrder[b['priority']])))
		#logging.info("Comparing ID: " + str(cmp(-a['id'], -b['id'])))
		return cmp(cls.issueStatusOrder[a['status']], cls.issueStatusOrder[b['status']]) or cmp(cls.issuePriorityOrder[a['priority']], cls.issuePriorityOrder[b['priority']]) or cmp(-a['id'], -b['id'])
	signature = db.TextProperty(required=True)
	signHash = db.StringProperty()
	count = db.IntegerProperty(required=True)
	lastIncident = db.DateTimeProperty()
	linked = db.BooleanProperty()
	issueName = db.IntegerProperty()
	fixed = db.BooleanProperty()
	status = db.StringProperty()
	priority = db.StringProperty()
	def updateStatusPriority(self):
		url = r"http://code.google.com/feeds/issues/p/ankidroid/issues/full?id=" + str(self.issueName)
		updated = False
		try:
			result = fetch(url)
			if result.status_code == 200:
				soup = BeautifulStoneSoup(result.content)
				status = soup.find('issues:status')
				if status:
					self.status = unicode(status.string)
					updated = True
					logging.debug("Setting status to '" + self.status + "'")
				priority = soup.find(name='issues:label', text=re.compile(r"^Priority-.+$"))
				if priority:
					self.priority = re.search("^Priority-(.+)$", unicode(priority.string)).group(1)
					updated = True
					logging.debug("Setting priority to '" + self.priority + "'")
		except Error, e:
			logging.error("Error while retrieving status and priority: %s" % str(e))
		return updated
	def findIssue(self):
		# format signature for google query
		urlEncodedSignature = re.sub(r'([:=])(\S)', r'\1 \2', self.signature)
		urlEncodedSignature = quote_plus(urlEncodedSignature)
		logging.debug("findIssue: URL-Encoded: '" + urlEncodedSignature + "'")
		url = r"http://code.google.com/p/ankidroid/issues/list?can=1&q=" + urlEncodedSignature + r"&colspec=ID+Status+Priority"
		try:
			result = fetch(url)
			if result.status_code == 200:
				#logging.debug("Results retrieved (" + str(len(result.content)) + "): '" + str(result.content) + "'")
				soup = BeautifulSoup(result.content)
				issueID = soup.findAll('td', {'class': 'vt id col_0'})
				issueStatus = soup.findAll('td', {'class': 'vt col_1'})
				issuePriority = soup.findAll('td', {'class': 'vt col_2'})
				logging.debug("findIssue: Issue found: " + str(issueID) + " " + str(issueStatus) + " " + str(issuePriority))
				issues = []
				for i, issue in enumerate(issueID):
					issues.append({'id': long(unicode(issueID[i].a.string)), 'status':	strip(unicode(issueStatus[i].a.string)), 'priority': strip(unicode(issuePriority[i].a.string))})
				issues.sort(Bug.compareIssues)
				logging.debug("findIssue: sorted results list: " + str(issues))
				return issues
		except Error, e:
			logging.error("findIssue: Error while querying for matching issues: %s" % str(e))
			return []

class CrashReport(db.Model):
	email = db.EmailProperty(required=True)
	crashId = db.StringProperty(required=True)
	report = db.TextProperty(required=True)
	packageName = db.StringProperty()
	versionName = db.StringProperty()
	crashSignature = db.TextProperty()
	signHash = db.StringProperty()
	crashTime = db.DateTimeProperty()
	sendTime = db.DateTimeProperty()
	brand = db.StringProperty()
	model = db.StringProperty()
	product = db.StringProperty()
	device = db.StringProperty()
	androidOSId = db.StringProperty()
	androidOSVersion = db.StringProperty()
	availableInternalMemory = db.IntegerProperty()
	tags = db.StringProperty()
	bugKey = db.ReferenceProperty(Bug)
	def linkToBug(self):
		results = db.GqlQuery("SELECT * FROM Bug WHERE signHash = :1", self.signHash)
		bug = results.get()
		if bug:
			logging.debug("Found existing bug")
			if self.bugKey != bug.key():
				logging.debug("Assigning to bug: %d" % bug.key().id())
				oldbug = self.bugKey
				self.bugKey = bug.key()
				self.put()
				bug.count += 1
				bug.lastIncident = self.crashTime
				bug.put()
				if oldbug:
					logging.debug("Reducing count (%d) of old bug: %d" % oldbug.count, oldbug.key().id())
					if oldbug.count == 1:
						logging.debug("Deleting old bug: %d" % oldbug.key().id())
						oldbug.delete()
					else:
						logging.debug("Old bug count: %d" % oldbug.count)
						oldbug.count -= 1
						oldbug.put()
			else:
				logging.debug("Same as old bug: %d" % oldbug.key().id())
		else:
			logging.debug("Created new bug")
			nb = Bug(signature = self.crashSignature, signHash = self.signHash, count = 1, lastIncident = self.crashTime, linked = False, fixed = False, status = '', priority = '')
			self.bugKey = nb.put()
			logging.debug("Linked to bug, new count: " + str(self.bugKey.count))
			self.put()
	@classmethod
	def parseUTCDateTime(cls, dt_str):
		m = re.match(r"(\w+ \w+ \d+ \d+:\d+:\d+ )(\S+)( \d+)",  dt_str)
		if m is None:
			logging.warning("Datetime has unknown format: '" + dt_str + "'")
			return (None, "format_unknown")
		try:
			tm = datetime.strptime(m.group(1) + m.group(3), r"%a %b %d %H:%M:%S %Y")
		except ValueError:
			logging.warning("Can't parse datetime from: '" + m.group(1) + m.group(3) + "'")
			return (None, "parsing_failed")
		try:
			tzname = m.group(2)
			tz = timezone(tzname)
		except UnknownTimeZoneError:
			# Alternative timezone formats
			newtzname = re.sub(r"^(\w+[+-])0*(\d*)[:.]00$", r"\1\2", tzname)
			newtzname = re.sub(r"^(GMT[+-]\d*)$", r"Etc/\1", newtzname)
			newtzname = re.sub(r"^(EDT)$", r"EST5\1", newtzname)
			newtzname = re.sub(r"^(CDT)$", r"CST6\1", newtzname)
			newtzname = re.sub(r"^(MDT)$", r"MST7\1", newtzname)
			newtzname = re.sub(r"^(PDT)$", r"PST8\1", newtzname)
			newtzname = re.sub(r"^JST$", r"Japan", newtzname)
			newtzname = re.sub(r"^CEST$", r"CET", newtzname)
			newtzname = re.sub(r"^MESZ$", r"Europe/Berlin", newtzname)
			logging.debug("Changed timezone from '" + tzname + "' to '" + newtzname + "'")
			try:
				tz = timezone(newtzname)
			except UnknownTimeZoneError:
				logging.warning("Unknown timezone: '" + tzname + "'")
				return (None, "timezone_unknown")
		try:
			tm = tz.localize(tm)
		except (ValueError, NonExistentTimeError):
			logging.warning("Error while localizing datetime '" + tm.strftime(r"%d/%m/%Y %H:%M:%S") + "' to '" + tz.zone + "'")
			return (None, "localizing_failed")
		logging.debug("UTC time parsed: '" + tm.astimezone(pytz.utc).strftime(r"%d/%m/%Y %H:%M:%S %Z") + "'")
		return (tm.astimezone(pytz.utc), "")
	@classmethod
	def getCrashSignature(cls, body):
		signLine1 = ''
		signLine2 = ''
		m1 = re.search(r"Begin Stacktrace\s*(<br>\s*)*([^<\s][^<]*[^<\s])\s*<br>", body, re.M|re.U)
		if m1:
			signLine1 = re.sub(r"\$[a-fA-F0-9@]*", "", m1.group(2))
		m2 = re.search(r"<br>\s*(at\scom\.ichi2\.anki\.[^<]*[^<\s])\s*<br>", body, re.M|re.U)
		if m2:
			signLine2 = re.sub(r"\$[a-fA-F0-9@]*", "", m2.group(1))
		return signLine1 + "\n" + signLine2
	#m = re.search(r".*<br>\s*(.*?com\.ichi2\.anki\..*?)<br>", body, re.M|re.U)
		#if m and m.groups():
	#		return re.sub(r"\$[a-fA-F0-9@]*", "", m.group(1))
		#return ""
	@classmethod
	def parseSimpleValue(cls, body, key, op=" = "):
		pattern = r"<br>\s*" + key + op + r"(<a>)?(.*?)(</a>)?<br>"
		m = re.search(pattern, body, re.M|re.U)
		if m and m.groups():
			logging.debug("Parsed value for key: '" + key + "' = '" + m.group(2) + "'")
			return m.group(2)
		else:
			logging.debug("Parsed nothing for key: '" + key +"'")
		return ""
	@classmethod
	def getMessageEssentials(cls, subject, body):
		m = re.search("^Bug Report on (.*)$", subject)
		if (m is None) or m.groups() is None:
			logging.warning("Hospitalizing message: Unknown subject (" + subject + ")")
			return (None, None, "", "unknown_subject")
		(send_ts, hospital_reason) = cls.parseUTCDateTime(m.group(1))
		if hospital_reason:
			logging.warning("Hospitalizing message: Failed in parsing send time")
			return (None, None, "", "send_ts_" + hospital_reason)
		else:
			logging.debug("Received on: " + send_ts.strftime(r"%d/%m/%Y %H:%M:%S %Z"))
		crash_str = cls.parseSimpleValue(body, "Report Generated", ": ")
		if not crash_str:
			logging.warning("Hospitalizing message: Missing generated time line in body")
			return (None, None, "", "crash_time_missing")
		(crash_ts, hospital_reason) = cls.parseUTCDateTime(crash_str)
		if hospital_reason:
			logging.warning("Hospitalizing message: Failed in parsing crash time")
			return (None, None, "", "crash_ts_" + hospital_reason)
		else:
			logging.debug("Crashed on: " + crash_ts.strftime(r"%d/%m/%Y %H:%M:%S %Z"))
		signature = cls.getCrashSignature(body)
		if signature:
			logging.debug("Signature: '" + signature + "'")
		else:
			logging.warning("Hospitalizing message: No signature found")
			return (None, None, "", "no_signature")
		return (send_ts, crash_ts, signature, "")
	def parseReport(self):
		(send_ts, crash_ts, signature, hospital_reason) = CrashReport.getMessageEssentials(self.crashId, self.report)
		if hospital_reason:
			return hospital_reason
		self.packageName = self.parseSimpleValue(self.report, "PackageName")
		self.versionName = self.parseSimpleValue(self.report, "VersionName")
		self.crashSignature = signature
		self.signHash = hashlib.sha256(signature).hexdigest()
		self.crashTime = crash_ts
		self.sendTime = send_ts
		self.brand = self.parseSimpleValue(self.report, "Brand")
		self.model = self.parseSimpleValue(self.report, "Model")
		self.product = self.parseSimpleValue(self.report, "Product")
		self.device = self.parseSimpleValue(self.report, "Device")
		self.androidOSId = self.parseSimpleValue(self.report, "ID")
		self.androidOSVersion = self.parseSimpleValue(self.report, "AndroidVersion")
		try:
			self.availableInternalMemory = long(self.parseSimpleValue(self.report, "AvailableInternalMemory"))
		except ValueError:
			logging.warning("Hospitalizing message: Failed in parsing available internal memory: '" + self.parseSimpleValue(self.report, "AvailableInternalMemory") + "'")
			return "avail_mem_parse_error"
		self.tags = self.parseSimpleValue(self.report, "Tags")
		self.linked = False
		self.bugId = 0
		self.issueLink = None
		#self.put()
		return ""

class LogSenderHandler(InboundMailHandler):
	def receive(self, mail_message):
		logging.info("Message from: " + mail_message.sender + " - Subject: " + mail_message.subject)
		body = ''
		try:
			# Get the body, try the html version, if not found we convert the plain to html
			body = mail_message.bodies('text/html').next()[1].decode()
		except StopIteration:
			logging.warning("Can't find html body, will use text/plain instead")
		if not body:
			try:
				body = mail_message.bodies('text/plain').next()[1]
				#logging.info("encoding... " + str(isinstance(body, EncodedPayload)))

				#if isinstance(body, EncodedPayload):
				logging.warning("Message encoding: " + body.encoding + " type: " + str(type(body)) + " type: " + str(type(body.payload)))
#				if body.encoding == "8bit":
#					body.encoding = '7bit' 
				#logging.info("encoded: " + body)
				body = body.decode()
				logging.debug("Message decoded: '" + body + "'")
				body = escape(body)
				body = re.sub(r"\n", "<br>", body)
				logging.debug("Message escaped: '" + body + "'")
			except StopIteration:
				logging.error("Rejecting message: Can't retrieve even text/plain body of mail")
				raise
		# Convert paragraphs to <br>
		body = re.sub(r"<p>", "", body)
		body = re.sub(r"</p>", "<br>", body)
		body = re.sub(r"<br\s*/>", "<br>", body, re.U)
		# Escape the report BEGIN/END marks so they are not killed as tags
		body = re.sub(r"-->\s*((BEGIN)|(END))\s+REPORT\s+(\d+)\s*<--", r"--&gt; \1 REPORT \4 &lt;--", body, re.U)
		# Remove anything following the END of REPORT (like personal email signatures)
		m = re.search(r'^(.*--\&gt; END REPORT \d \&lt;--).*$', body, re.S)
		if m:
			body = m.group(1)
		# Strip all tags except <br>
		body = re.sub(r'<(?!br/?>)[^>]+>', '', body)
		cr = CrashReport(email = mail_message.sender, crashId = mail_message.subject, report = body)
		hospital_reason = cr.parseReport()
		if hospital_reason:
			logging.info("Hospitalized body: '" + body)
			hr = HospitalizedReport(email=mail_message.sender,
					crashId=mail_message.subject,
					crashBody=body,
					diagnosis=hospital_reason,
					processed=False)
			hr.put()
		else:
			# check for duplicates
			dupl_query = CrashReport.all()
			dupl_query.filter("crashId =", cr.crashId)
			if dupl_query.count(1) == 0:
				cr.put()
				cr.linkToBug()
			else:
				dupl = dupl_query.fetch(1)[0]
				logging.warning("Found duplicate with id: " + str(dupl.key().id()))

def main():
	application = webapp.WSGIApplication([LogSenderHandler.mapping()], debug=True)
	run_wsgi_app(application)

if __name__ == '__main__':
	main()

