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
	crashId = db.StringProperty(required=True)
	crashBody = db.TextProperty()
	diagnosis = db.StringProperty()

class Issue(db.Model):
	issueLink = db.LinkProperty()
	fixed = db.BooleanProperty()

class Bug(db.Model):
	signature = db.StringProperty(required=True)
	count = db.IntegerProperty(required=True)
	lastIncident = db.DateTimeProperty()
	linked = db.BooleanProperty()
	issueName = db.IntegerProperty()

class CrashReport(db.Model):
	crashId = db.StringProperty(required=True)
	packageName = db.StringProperty(required=True)
	versionName = db.StringProperty(required=True)
	crashSignature = db.StringProperty(required=True)
	email = db.EmailProperty(required=True)
	crashTime = db.DateTimeProperty(required=True)
	sendTime = db.DateTimeProperty(required=True)
	brand = db.StringProperty()
	model = db.StringProperty()
	product = db.StringProperty()
	device = db.StringProperty()
	androidOSId = db.StringProperty()
	androidOSVersion = db.StringProperty()
	availableInternalMemory = db.IntegerProperty()
	tags = db.StringProperty()
	report = db.TextProperty()
	bugKey = db.ReferenceProperty(Bug)
	def addToBug(self):
		if not self.bugKey:
			results = db.GqlQuery("SELECT * FROM Bug WHERE signature = :1", self.crashSignature)
			bug = results.get()
			if bug:
				logging.debug("Found old bug")
				self.bugKey = bug.key()
				bug.count+=1
				bug.lastIncident = self.crashTime
				bug.put()
			else:
				logging.debug("Created new bug")
				nb = Bug(signature = self.crashSignature,
						count = 1,
						lastIncident = self.crashTime)
				self.bugKey = nb.put()
			logging.debug("Linked to bug, new count: " + str(self.bugKey.count))
			self.put()

class LogSenderHandler(InboundMailHandler):
	def parseUTCDateTime(self, dt_str):
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
			newtzname = re.sub(r"^(\w+[+-])0*(\d*):00$", r"\1\2", tzname)
			newtzname = re.sub(r"^(GMT[+-]\d*)$", r"Etc/\1", newtzname)
			newtzname = re.sub(r"^(EDT)$", r"EST5\1", newtzname)
			newtzname = re.sub(r"^(CDT)$", r"CST6\1", newtzname)
			newtzname = re.sub(r"^(MDT)$", r"MST7\1", newtzname)
			newtzname = re.sub(r"^(PDT)$", r"PST8\1", newtzname)
			logging.info("Changed timezone from '" + tzname + "' to '" + newtzname + "'")
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

	def getCrashSignature(self, mail):
		m = re.search(r"(.*com\.ichi2\.anki\..*)<br>", mail)
		if m and m.groups():
			return re.sub(r"\$[a-fA-F0-9@]*", "", m.group(1))
		return ""

	def parseSimpleValue(self, mail, key, op=" = "):
		pattern = key + op + r"(.*)<br>"
		m = re.search(pattern, mail)
		if m and m.groups():
			logging.debug("Parsed simple value: '" + key + "' = '" + m.group(1) + "'")
			return m.group(1)
		return ""

	def getMessageEssentials(self, subject, body):
		m = re.search("^Bug Report on (.*)$", subject)
		if (m is None) or m.groups() is None:
			logging.warning("Hospitalizing message: Unknown subject (" + subject + ")")
			return (None, None, "", "unknown_subject")
		(send_ts, hospital_reason) = self.parseUTCDateTime(m.group(1))
		if hospital_reason:
			logging.warning("Hospitalizing message: Failed in parsing send time")
			return (None, None, "", "send_ts_" + hospital_reason)
		else:
			logging.info("Received on: " + send_ts.strftime(r"%d/%m/%Y %H:%M:%S %Z"))
		crash_str = self.parseSimpleValue(body, "Report Generated", ": ")
		if not crash_str:
			logging.warning("Hospitalizing message: Missing generated time line in body")
			return (None, None, "", "crash_time_missing")
		(crash_ts, hospital_reason) = self.parseUTCDateTime(crash_str)
		if hospital_reason:
			logging.warning("Hospitalizing message: Failed in parsing crash time")
			return (None, None, "", "crash_ts_" + hospital_reason)
		else:
			logging.info("Crashed on: " + crash_ts.strftime(r"%d/%m/%Y %H:%M:%S %Z"))
		signature = self.getCrashSignature(body)
		if signature:
			logging.info("Signature: '" + signature + "'")
		else:
			logging.warning("Hospitalizing message: No signature found")
			return (None, None, "", "no_signature")
		return (send_ts, crash_ts, signature, "")

	def receive(self, mail_message):
		logging.info("Message from: " + mail_message.sender)
		logging.info("Subject: " + mail_message.subject)
#		try:
#			body = mail_message.bodies('text/plain').next()[1].decode()
#			logging.info("Received body: '" + body + "'")
#		except StopIteration:
#			logging.info("Can't retrieve html body of mail")
		try:
			body = mail_message.bodies('text/html').next()[1].decode()
		except StopIteration:
			logging.warning("Rejecting message: Can't retrieve body of mail")
			return
		body = re.sub(r"<p>", "", body)
		body = re.sub(r"</p>", "<br>", body)
#		logging.info("Received html body: '" + body + "'")
		(send_ts, crash_ts, signature, hospital_reason) = self.getMessageEssentials(mail_message.subject, body)

		if hospital_reason:
			cr = HospitalizedReport(crashId=mail_message.subject,
					crashBody=body,
					diagnosis=hospital_reason)
			cr.put()
		else:
			cr = CrashReport(crashId=mail_message.subject,
					packageName = self.parseSimpleValue(body, "PackageName"),
					versionName = self.parseSimpleValue(body, "VersionName"),
					crashSignature = signature,
					email = db.Email(mail_message.sender),
					crashTime = crash_ts,
					sendTime = send_ts,
					brand = self.parseSimpleValue(body, "Brand"),
					model = self.parseSimpleValue(body, "Model"),
					product = self.parseSimpleValue(body, "Product"),
					device = self.parseSimpleValue(body, "Device"),
					androidOSId = self.parseSimpleValue(body, "Board"),
					androidOSVersion = self.parseSimpleValue(body, "AndroidVersion"),
					availableInternalMemory = long(self.parseSimpleValue(body, "AvailableInternalMemory")),
					tags = self.parseSimpleValue(body, "Tags"),
					report = body,
					linked = False,
					bugId = 0,
					issueLink = None)
			cr.put()
			cr.addToBug()

def main():
	application = webapp.WSGIApplication([LogSenderHandler.mapping()], debug=True)
	run_wsgi_app(application)
	#wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
	main()

