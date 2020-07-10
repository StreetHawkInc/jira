import logging
from IPython.core.magic import (Magics, magics_class, line_magic,
                                cell_magic, line_cell_magic)
import re
from tabulate import tabulate
from pprint import pprint
from datetime import datetime
import yaml
import jmespath
from IPython.core.magic_arguments import (
    argument, magic_arguments,
    parse_argstring,
)
import shlex
from docopt import docopt
from subprocess import Popen
from pygments.lexers import YamlLexer
from pygments.formatters import Terminal256Formatter
from pygments import highlight



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
        if issue.fields.customfield_10020:
            for sprint in issue.fields.customfield_10020:
                try:
                    results.append(
                        re.search(".*,name=(?P<name>.*?),.*", sprint, re.MULTILINE).groupdict()['name'])
                except:
                    logging.exception("unmatched sprint %s", sprint)
        return results

    @line_magic
    def sprints(self, line=None):
        pprint(self.boards)

    @line_magic
    def search(self, line):
        self.results = []
        if 'order by' not in line.lower():
            line += ' ORDER BY updated DESC, created DESC'
        for issue in self.jira.search_issues(line, maxResults=10):
            self.results.append(
                [
                    issue.key,
                    issue.fields.summary,
                    ",".join(self.get_sprint(issue)),
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
        print("Current Sprint : %s <id:%s>" % (sprint, sprint.id))
        print(tabulate(results))

    @line_magic
    def mysprint(self, line=''):
        results = []
        sprint = self._current_sprint()
        query = 'sprint = %s AND status in ("In Progress", Open) AND assignee = currentUser()' % sprint.id
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

    @magic_arguments()
    @argument('-o', '--output', help='Print output format.')
    @argument('id', type=str, help='Issue id.')
    @line_magic
    def show(self, args):
        """ Get Issue by id
        """
        args = parse_argstring(self.show, args)
        self.pprint(self.jira.issue(args.id))

    def pprint(self, jissue):
        issue = {}
        FIELD_MAP = {
            'key': 'key',
            'summary': 'fields.summary',
            'description': 'fields.description',
            'reporter': 'fields.reporter.displayName',
            'assignee': 'fields.assignee.displayName',
            'status': 'fields.status.name',
            'sprint': 'fields.currentSprint',
        }
        for field, source in FIELD_MAP.items():
            issue[field] = jmespath.search(source, jissue.raw)

        yml = yaml.dump(issue)
        print(highlight(yml, YamlLexer(), Terminal256Formatter()))

    @line_magic
    def create_task(self, line=''):
        args = docopt(
            """ Create a Task

            Usage:
            create_task <summary> <description> [--project=<project>|--assignee=<assignee>]

            Options:
            --project=<project>  Project to use [default: POINTZI]
            --assigee=<assignee>  Project to use [default: currentUser()]
            """,
            argv=shlex.split(line),
        )
        issue = {
            "summary": args['<summary>'],
            "description": args['<description>'],
            "project": args['--project'],
            "issuetype": "Task",
        }
        if args['--assignee']:
            issue['assignee'] = args['--assignee']
        issue = self.jira.create_issue(issue)
        import ipdb;ipdb.set_trace()
        self.pprint(issue)

    @line_magic
    def open(self, line=""):
        args = docopt(
            """ Open issue in browser

            Usage:
                open <id>

            Options:
                --browser=<browser>  default browser to use [default: xdg]
            """,
            argv=shlex.split(line),
        )
        issue = self.jira.issue(args['<id>'])
        Popen(['browser', issue.permalink()])

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

    @line_magic
    def recentlyviewed(self, line=''):
        return self.search('order by lastViewed DESC')


    @line_magic
    def recentlyviewedopen(self, line=''):
        return self.search('status in ("In Progress", Open, Pending, Reopened, Testing, "Waiting for QA", "Work in progress") order by lastViewed DESC')

    @line_magic
    def myrecentlyviewedopen(self, line=''):
        return self.search('status in ("In Progress", Open, Pending, Reopened, Testing, "Waiting for QA", "Work in progress") AND assignee in (currentUser()) order by lastViewed DESC')

    @line_magic
    def recentlycreated(self, line=''):
        return self.search('status in ("In Progress", Open, Pending, Reopened, Testing, "Waiting for QA", "Work in progress") ORDER BY created DESC, lastViewed DESC')

    @line_magic
    def myrecentlycreated(self, line=''):
        return self.search('status in ("In Progress", Open, Pending, Reopened, Testing, "Waiting for QA", "Work in progress") AND assignee in (currentUser()) ORDER BY created DESC, lastViewed DESC')

    @line_magic
    def delete(self, line=''):
        self.jira.issue(line).delete()

    @line_magic
    def assign(self, line=''):
        args = docopt(
            """Assign issue
            Usage:
            assign <id> <nick>
            """,
            argv=shlex.split(line)
        )
        USERS = {
            "sue": "5b5587607501ba2d6ea64178",
            "john": "5ae2734c424d6b2e29a09fd4",
            "dl": "5b8894114d21642beb80e399",
            "vinh": "557058:3dd1d88e-2649-473a-9e8b-0671237c77dc",
            "joao": "5d895e4a4831170dbc8f0e77",
            "narsing": "5cf4ba8198b1560e859973b3",
            "ganesh": "5cf4ba8198b1560e859973b3",
            "steven": "557058:61e4c007-f72f-4500-870e-594e73520785",
        }
        
        print(
            self.jira.assign_issue(
                self.jira.issue(args['<id>']),
                account_id=USERS.get(args['<nick>'], args['<nick>'])
            )
        )
    @line_magic
    def comment(self, line=''):
        args = docopt(
            """comment on issue
            Usage:
                comment <id> <comment>
            """,
            argv=shlex.split(line)
        )
        pprint(
            self.jira.add_comment(
                self.jira.issue(args['<id>']),
                args['<comment>'],
            )
        )
    def print_comment(self, comment):
        _comment = {}
        FIELD_MAP = {
            'id': 'id',
            'author': 'author.displayName',
            'body': 'body',
            'created': 'created',
            'updated': 'updated',
        }
        for field, source in FIELD_MAP.items():
            _comment[field] = jmespath.search(source, comment.raw)

        print(highlight(yaml.dump(_comment), YamlLexer(), Terminal256Formatter()))


    @line_magic
    def comments(self, line=''):
        args = docopt(
            """get issue comments
            Usage:
                comments <id>
            """,
            argv=shlex.split(line)
        )
        for comment in self.jira.comments(
                self.jira.issue(args['<id>']),
        ):
            self.print_comment(comment)

    @line_magic
    def reportedbyme(self, line=''):
        return self.search('reporter in (currentUser()) ORDER BY updated DESC, created DESC, lastViewed DESC')

    @line_magic
    def transition(self, line=''):
        TRANSITIONS = {
            'open': 'Open',
            'dev': '81',
            'testing': '31',
            'qa': '211', # Waiting for QA
            'start':  '11', # Start Development
        }
        args = docopt(
            """transition issue to %s
            Usage:
                assign <id> <transition> [<comment>]
            """ % TRANSITIONS,
            argv=shlex.split(line)
        )
        print(
            self.jira.transition_issue(
                self.jira.issue(args['<id>']),
                TRANSITIONS[args['<transition>']],
                comment=args.get('<comment>'),
            )
        )
