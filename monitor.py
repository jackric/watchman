#!/usr/bin/env python2.7
"""
Uptime monitor
Reads monitor.config and regularly monitors "Sites" to ensure they are
responding. The configured Admin will be sent an email when a Site goes down
"""
import ConfigParser
import logging
import logging.handlers
import urllib2
import sys
import smtplib
import threading
import time

# Set up logging to console and to syslog
log = logging.getLogger("site-watcher")
log.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(name)s: %(message)s")
syslog_handler = logging.handlers.SysLogHandler(address="/dev/log")
syslog_handler.setFormatter(formatter)
for h in (stream_handler, syslog_handler):
    log.addHandler(h)


class Client(object):
    """
    Implements get_url for checking a URL, hiding the implementation
    """

    def __init__(self, user_agent, timeout=5):
        self._user_agent = user_agent
        self._timeout = float(timeout)

    def get_url(self, url):
        request = urllib2.Request(url, headers={"User-Agent":
                                                self._user_agent})
        try:
            urllib2.urlopen(request, timeout=self._timeout)
        except urllib2.URLError, e:
            return False, e.reason
        return True, None


class Site(object):
    def __init__(self, name, url, watch_interval, admin_email):
        self.name = name
        self.url = url
        self.watch_interval = float(watch_interval)
        self.admin_email = admin_email
        self.last_error = ""
        self.up = True

    def check_is_up(self, client):
        self.up, self.last_error = client.get_url(self.url)

    def __repr__(self):
        return "<Site %s url: %s>" % (self.name, self.url)


class ConfigReader(object):
    def __init__(self, config_path):
        self._config_path = config_path
        self.parser = ConfigParser.ConfigParser()
        self.parser.read(config_path)
        self.admins = dict(self.get_admins(self.parser))
        self.sites = list(self.get_sites())
        self.client = self.construct_client()
        self.emailer = self.get_emailer()

    def get_emailer(self):
        conf = dict(self.parser.items("SMTP"))
        return Emailer(**conf)

    def construct_client(self):
        conf = dict(self.parser.items("Client"))
        return Client(conf["user-agent"], conf["timeout"])

    @staticmethod
    def sections_of_type(parser, section_type):
        """Convenience function for iterating over sections of a type
        e.g. [Site BlahBlah], giving name and the settings as a dict"""
        for section_name in parser.sections():
            parts = section_name.split(None, 1)
            if len(parts) == 2 and parts[0] == section_type:
                yield parts[1], dict(parser.items(section_name))

    @classmethod
    def get_admins(cls, parser):
        for admin_name, conf in cls.sections_of_type(parser, "Admin"):
            yield admin_name, conf['email']

    def get_sites(self):
        for site_name, conf in self.sections_of_type(self.parser, "Site"):
            admin_email = self.admins[conf['admin']]
            watch_interval = conf.get("watch_interval", 60)
            yield Site(site_name, conf['url'], watch_interval,
                       admin_email)


class SiteWatcher(threading.Thread):
    """Periodically checks the site for up-ness and emails the admin of
    the site if the site is down"""

    def __init__(self, site, client, emailer):
        threading.Thread.__init__(self)
        self.site = site
        self.client = client
        self.emailer = emailer

    def run(self):
        while True:
            self.site.check_is_up(self.client)
            if not self.site.up:
                log.info("%s down" % self.site)
                self.emailer.send_message(self.site.admin_email,
                                         "Site %s down" % self.site,
                                         self.site.last_error)
            else:
                log.debug("%s up" % self.site)
            time.sleep(self.site.watch_interval)


class Emailer(object):
    def __init__(self, sender_name, sender_email, smtp_host):
        self.sender_name = sender_name
        self.sender_email = sender_email
        self.smtp = smtplib.SMTP(smtp_host)

    def send_message(self, to, subject, text):
        sender_name, sender_email = self.sender_name, self.sender_email
        message = """\
From: %(sender_name)s <%(sender_email)s>
To: %(to)s
Subject: %(subject)s

%(text)s
""" % locals()
        try:
            self.smtp.sendmail(self.sender_email, to, message)
        except smtplib.SMTPException, e:
            log.error("Couldn't email %s" % to)
            log.error(e)


def main():
    if len(sys.argv[1]) > 0 and sys.argv[1] == "--debug":
        log.setLevel(logging.DEBUG)
    config = ConfigReader("monitor.config")
    watchers = []
    for site in config.sites:
        watcher = SiteWatcher(site, config.client, config.emailer)
        watcher.start()
        watchers.append(watcher)

    for watcher in watchers:
        watcher.join()

if __name__ == "__main__":
    main()
