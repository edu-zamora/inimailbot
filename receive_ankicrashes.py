import logging, email, re
from datetime import datetime
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

from pytz.gae import pytz
from pytz import timezone, UnknownTimeZoneError

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
	crashSignature = db.StringProperty()
	email = db.EmailProperty()
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
	report = db.TextProperty()
	hospitalized = db.BooleanProperty()
	bugKey = db.ReferenceProperty(Bug)
	def addToBug(self):
		if (not self.hospitalized) and (not self.bugKey):
			results = db.GqlQuery("SELECT * FROM Bug WHERE signature = :1", self.crashSignature)
			bug = results.get()
			if bug:
				logging.info("found old bug")
				self.bugKey = bug.key()
				bug.count+=1
				bug.lastIncident = self.crashTime
				bug.put()
			else:
				logging.info("created new bug")
				nb = Bug(signature = self.crashSignature,
						count = 1,
						lastIncident = self.crashTime)
				self.bugKey = nb.put()
			logging.info("linked to bug: " + str(self.bugKey.count))
			self.put()

class LogSenderHandler(InboundMailHandler):
	def parseUTCDateTime(self, dt_str):
		m = re.match(r"(\w+ \w+ \d+ \d+:\d+:\d+ )(\S+)( \d+)",  dt_str)
		if m is None:
			logging.info("Datetime has unknown format: '" + dt_str + "'")
			return None
		try:
			tm = datetime.strptime(m.group(1) + m.group(3), r"%a %b %d %H:%M:%S %Y")
		except ValueError:
			logging.info("Can't parse datetime from: '" + m.group(1) + m.group(3) + "'")
			return None
		try:
			tz = timezone(m.group(2))
		except UnknownTimeZoneError:
			logging.info("Unknown time zone: " + m.group(2) + "'")
			return None
		try:
			tm = tz.localize(tm)
		except (ValueError, NonExistentTimeError):
			logging.info("Error while localizing datetime '" + tm.strftime(r"%d/%m/%Y %H:%M:%S") + "' to '" + tz.zone + "'")
			return None
		return tm.astimezone(pytz.utc)

	def getCrashSignature(self, mail):
		m = re.search(r"(.*com\.ichi2\.anki\..*)\n", mail)
		if m and m.groups():
			return re.sub(r"\$[0-9@]*", "", m.group(1))
		return ""

	def parseSimpleValue(self, mail, key, op=" = "):
		pattern = key + op + r"(.*)\n"
		m = re.search(pattern, mail)
		if m and m.groups():
			#logging.info(key + " = " + m.group(1))
			return m.group(1)
		return ""

	def receive(self, mail_message):
		logging.info("-----------------------")
		logging.info("Received a message from: " + mail_message.sender)
		logging.info("Subject: " + mail_message.subject)
		m = re.search("^Bug Report on (.*)$", mail_message.subject)
		if (m is None) or m.groups() is None:
			logging.info("Rejecting message due to unknown subject: " + mail_message.subject)
			return
		utc_ts = self.parseUTCDateTime(m.group(1))
		if utc_ts is None:
			logging.info("Rejecting message due to wrong format of subject: " + mail_message.subject)
			return
		logging.info("Received on: " + utc_ts.strftime(r"%d/%m/%Y %H:%M:%S %Z"))
		try:
			body = mail_message.bodies('text/plain').next()[1].decode()
		except StopIteration:
			logging.info("Can't retrieve body of mail")
		signature = self.getCrashSignature(body)
		logging.info("Signature: " + signature)
		if signature:
			sendToHospital = False
		else:
			sendToHospital = True
		cr = CrashReport(crashId=mail_message.subject,
				packageName = self.parseSimpleValue(body, "PackageName"),
				versionName = self.parseSimpleValue(body, "VersionName"),
				crashSignature = signature,
				email = db.Email(mail_message.sender),
				crashedTime = self.parseUTCDateTime(self.parseSimpleValue(body, "Report Generated", ": ")),
				sendTime = utc_ts,
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
				issueLink = None,
				hospitalized = sendToHospital)
		cr.put()
		cr.addToBug()


def main():
	application = webapp.WSGIApplication([LogSenderHandler.mapping()], debug=True)
	run_wsgi_app(application)
	#wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
	main()

