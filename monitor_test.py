#!/usr/bin/env python

import unittest
from monitor import Client, Emailer, SiteWatcher, Site
import logging
log = logging.getLogger("site-watcher")
log.setLevel(logging.ERROR)


class FailyClient(Client):
    """Always behaves like Site is down"""

    def __init__(self, *args):
        pass

    def get_url(self, url):
        return False, "faily client"


class MockEmailer(Emailer):
    def __init__(self):
        self.mock_calls = []

    def send_message(self, *args):
        self.mock_calls.append(args)


class TestWatcher(unittest.TestCase):
    def setUp(self):
        self.client = FailyClient()
        self.site = Site("TestSite", "http://testsite.com", 2, "joe@bloggs.com")
        self.emailer = MockEmailer()
        self.watcher = SiteWatcher(self.site, self.client, self.emailer,
                                   fork=False)

    def test_email_sent(self):
        self.watcher.run_check()
        email_args = ("joe@bloggs.com",
                      "Site <Site TestSite url: http://testsite.com> down",
                      "faily client")
        self.assertIn(email_args, self.emailer.mock_calls)


if __name__ == '__main__':
    unittest.main()

