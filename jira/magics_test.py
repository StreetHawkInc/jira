from __future__ import absolute_import
from unittest import TestCase
from jira import JIRA
from jira.magics import JiraMagics
from mock import Mock


class TestJiraMagics(TestCase):
    def setUp(self):
        basic_auth = (
            "steven@streethawk.com",
            "dieX8bie",
        )
        options = {'verify': True, 'server': 'https://streethawk.atlassian.net'}
        self.jira = JIRA(options=options, basic_auth=basic_auth, oauth=None)

    def test_search(self):
        magics = JiraMagics(None, self.jira)
        magics.search("sprint = 44")

    def test_current_sprint(self):
        magics = JiraMagics(None, self.jira)
        magics.current_sprint()

    def test_show(self):
        magics = JiraMagics(Mock(), self.jira)
        magics.show('nick')
