from IPython.core.magic import (Magics, magics_class, line_magic,
                                cell_magic, line_cell_magic)
import re
from tabulate import tabulate
from pprint import pprint
from datetime import datetime


@magics_class
class JiraMagics(Magics):
    "Magics that hold additional state"

    def __init__(self, shell, jira):
        # You must call the parent constructor
        super(JiraMagics, self).__init__(shell)
        self.jira = jira
        self.boards = {}
        self.load_sprints()
        if shell:
            self.shell.user_ns['boards'] = self.boards

    @line_magic
    def load_sprints(self, line=None):
        for board in self.jira.boards():
            sprint_map = self.boards.setdefault((board.name, board.id), {})
            for sprint in self.jira.sprints(board.id):
                sprint_map[sprint.name] = sprint
        print("fetched sprints")

    def get_sprint(self, issue, active=True):
        results = []
        for sprint in issue.fields.customfield_10020:
            results.append(
                re.match(".*,name=(?P<name>.*?),.*", sprint).groupdict()['name'])
        return results

    @line_magic
    def sprints(self, line=None):
        pprint(self.boards)

    @line_magic
    def search(self, line):
        "my line magic"
        if self.shell:
            print("Full access to the main IPython object:", self.shell)
            print("Variables in the user namespace:", list(self.shell.user_ns.keys()))
        self.results = []
        for issue in self.jira.search_issues(line, maxResults=200):
            self.results.append(
                [
                    issue.key,
                    issue.fields.summary,
                    self.get_sprint(issue),
                ]
            )

        print(tabulate(self.results, tablefmt='plain'))

    def _current_sprint(self, qa=False):
        for board, sprint_map in self.boards.items():
            for sprint_name, sprint in sprint_map.items():
                if sprint.state == 'ACTIVE' and 'QA' not in sprint.name:
                    return sprint

    @line_magic
    def current_sprint(self, line=''):
        results = []
        sprint = self._current_sprint()
        query = 'sprint = %s AND status in ("In Progress", Open)' % sprint.id
        print(query)
        if line:
            query += ' AND ' + line
        for cnt, issue in enumerate(self.jira.search_issues(query, maxResults=500)):
            results.append(
                [
                    cnt,
                    issue.key,
                    issue.fields.summary,
                ]
            )
        print("Current Sprint : %s %s" % (sprint, sprint.id))
        print(tabulate(results))

    @line_magic
    def roll_sprint(self):
        self.load_sprints()
        sprint = self._current_sprint()
        input("closing sprint %s" % sprint)
        print(self.jira.update_sprint(sprint.id, state='closed'))
        qaitems = [
            x.key for x in
            self.jira.search_issues(
                "sprint = %s AND status = 'Waiting for QA'"
                % sprint.id
            )
        ]
        qasprint = self.jira.create_sprint(datetime.now().strftime("Pointzi Week %W"))
        print("Created sprint %s" % qasprint)
        self.jira.add_issues_to_sprint(qasprint.id, qaitems)
