import logging, email, re
from datetime import datetime
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

from pytz.gae import pytz
from pytz import timezone, UnknownTimeZoneError

class HospitalizedReport(db.Model):
	email = db.StringProperty(required=True)
	crashId = db.StringProperty(required=True)
	crashBody = db.TextProperty(required=True)
	diagnosis = db.StringProperty()

class Bug(db.Model):
	signature = db.StringProperty(required=True)
	count = db.IntegerProperty(required=True)
	lastIncident = db.DateTimeProperty()
	linked = db.BooleanProperty()
	issueName = db.IntegerProperty()
	fixed = db.BooleanProperty()
	#status = db.StringProperty()
	#priority = db.StringProperty()

class CrashReport(db.Model):
	email = db.EmailProperty(required=True)
	crashId = db.StringProperty(required=True)
	report = db.TextProperty(required=True)
	packageName = db.StringProperty()
	versionName = db.StringProperty()
	crashSignature = db.StringProperty()
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
		results = db.GqlQuery("SELECT * FROM Bug WHERE signature = :1", self.crashSignature)
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
			nb = Bug(signature = self.crashSignature, count = 1, lastIncident = self.crashTime, linked = False, fixed = False)
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
		m = re.search(r"<br>\s*(.*?com\.ichi2\.anki\..*?)<br>", body, re.M)
		if m and m.groups():
			return re.sub(r"\$[a-fA-F0-9@]*", "", m.group(1))
		return ""
	@classmethod
	def parseSimpleValue(cls, body, key, op=" = "):
		pattern = r"<br>\s*" + key + op + r"(<a>)?(.*?)(</a>)?<br>"
		m = re.search(pattern, body, re.M)
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
		self.put()
		return ""

class LogSenderHandler(InboundMailHandler):
	def receive(self, mail_message):
		logging.info("Message from: " + mail_message.sender + " - Subject: " + mail_message.subject)
		try:
			body = mail_message.bodies('text/html').next()[1].decode()
		except StopIteration:
			logging.warning("Rejecting message: Can't retrieve body of mail")
			return
		# Convert paragraphs to <br>
		body = re.sub(r"<p>", "", body)
		body = re.sub(r"</p>", "<br>", body)
		# Remove anything following the END of REPORT (like personal email signatures)
		m = re.search(r'^(.*--\&gt; END REPORT \d \&lt;--).*$', cr.report, re.S)
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
					diagnosis=hospital_reason)
			hr.put()
		else:
			cr.linkToBug()

def main():
	application = webapp.WSGIApplication([LogSenderHandler.mapping()], debug=True)
	run_wsgi_app(application)
	#wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
	main()

