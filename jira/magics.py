import logging
import functools
import sys
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
from docopt import docopt, DocoptExit
from subprocess import Popen
from pygments.lexers import YamlLexer
from pygments.formatters import Terminal256Formatter
from pygments import highlight
from jira.exceptions import JIRAError


def docoptwrapper(function):
    """
    A decorator that wraps the passed in function and logs 
    exceptions should one occur
    """
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (SystemExit, DocoptExit) as e:
            print(getattr(e, 'usage', ''))
    return wrapper


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
        self.USERS = {
            "sue": "5b5587607501ba2d6ea64178",
            "john": "5ae2734c424d6b2e29a09fd4",
            "dl": "5b8894114d21642beb80e399",
            "vinh": "557058:3dd1d88e-2649-473a-9e8b-0671237c77dc",
            "joao": "5d895e4a4831170dbc8f0e77",
            "narsing": "5cf4ba8198b1560e859973b3",
            "ganesh": "5cf4ba8198b1560e859973b3",
            "steven": "557058:61e4c007-f72f-4500-870e-594e73520785",
        }
        self.FIELD_MAP = {
            'key': 'key',
            'summary': 'fields.summary',
            'description': 'fields.description',
            'reporter': 'fields.reporter.displayName',
            'assignee': 'fields.assignee.displayName',
            'status': 'fields.status.name',
            'sprint': 'fields.currentSprint',
            'labels': 'fields.labels',
            'project': 'fields.project.key',
            'issuetype': 'fields.issuetype.name',
            'tester': 'customfield_10500.displayName',
        }

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
        args = docopt(
            """Get sprints

            Usage:
                sprints [options]

                -p --project=<project>  Project to use [default: POINTZI]
                -a --assignee=<assignee>  Project to use [default: currentUser()]
                -t --issuetype=<issuetype>  Issuetype to use [default: task]
            """,
            argv=shlex.split(line),
        )
        results = []
        sprint = self._current_sprint()
        args['sprintid'] = sprint.id
        args['assignee'] = self.resolve_user(args.get('--assignee'))
        query = 'sprint = {sprintid} AND status in ("In Progress", Open) AND assignee = {assignee}'.format(
            **args)
        print(query)
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
                    ",".join(issue.fields.labels),
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
        query = 'sprint = %s AND status in ("In Progress", "Open") AND assignee = currentUser()' % sprint.id
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
        for field, source in self.FIELD_MAP.items():
            issue[field] = jmespath.search(source, jissue.raw)

        yml = yaml.dump(issue)
        print(highlight(yml, YamlLexer(), Terminal256Formatter()))

    def resolve_user(self, user):
        return self.USERS.get(user, user)

    @line_magic
    @docoptwrapper
    def create(self, line=''):
        ISSUE_TYPES = {
            "task": "Task",
            "bug": "Bug",
            "feature": "New Feature",
            "support": "Support",
            "subtask": "Sub-Task",
            "epic": "Epic",
            "story": "Story",
        }
        args = docopt(
            """Create an issue

            Usage:
                create [options] <summary> <description>

                -p --project=<project>  Project to use [default: POINTZI]
                -a --assignee=<assignee>  Project to use [default: currentUser()]
                -t --issuetype=<issuetype>  Issuetype to use [default: task]
                -e --epicname=<epicname> Epic name
            """,
            argv=shlex.split(line),
        )
        issuetype = ISSUE_TYPES[args['--issuetype']]
        issue = {
            "summary": args['<summary>'],
            "description": args['<description>'],
            "project": args['--project'],
            "issuetype": issuetype,
        }
        if args['--assignee']:
            issue['assignee'] = self.resolve_user(args['--assignee'])
        if args['--issuetype'] == 'epic':
            issue['customfield_10018'] = args['--epicname']
        issue = self.jira.create_issue(issue)
        self.pprint(issue)

    @line_magic
    @docoptwrapper
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
        args = docopt(
            """Delete issue
            Usage:
                delete <id>
            """,
            argv=shlex.split(line)
        )
        self.jira.issue(args['<id>']).delete()

    @line_magic
    @docoptwrapper
    def clone(self, line=''):
        CLONE_FIELDS = dict(self.FIELD_MAP)
        CLONE_FIELDS.pop('sprint')
        CLONE_FIELDS.pop('status')
        CLONE_FIELDS.pop('key')
        CLONE_FIELDS.pop('reporter')
        args = docopt(
            """Cone issue
            Usage:
                clone <id>
            """,
            argv=shlex.split(line)
        )
        i0 = self.jira.issue(args['<id>'])
        issue = {}
        for field, source in CLONE_FIELDS.items():
            issue[field] = jmespath.search(source, i0.raw)
        self.pprint(self.jira.create_issue(issue))

    @line_magic
    @docoptwrapper
    def move(self, line=''):
        args = docopt(
            """Move issue to another project
            Usage:
                move <id> <project>
            """,
            argv=shlex.split(line)
        )
        i0 = self.jira.issue(args['<id>'])
        issue = {}
        for field, source in self.FIELD_MAP.items():
            issue[field] = jmespath.search(source, i0.raw)
        issue['project'] = args['<project>']
        self.pprint(self.jira.create_issue(**issue))

    @line_magic
    @docoptwrapper
    def assign(self, line=''):
        args = docopt(
            """Assign issue
            Usage:
            assign <id> <nick>
            """,
            argv=shlex.split(line)
        )
        print(
            self.jira.assign_issue(
                self.jira.issue(args['<id>']),
                account_id=self.USERS.get(args['<nick>'], args['<nick>'])
            )
        )
    @line_magic
    @docoptwrapper
    def comment(self, line=''):
        args = docopt(
            """comment on issue
            Usage:
                comment <id> <comment>
            """,
            argv=shlex.split(line)
        )
        regex = re.compile(r"(?<![@\w])@(\w{1,25})")
        pprint(
            self.jira.add_comment(
                self.jira.issue(args['<id>']),
                regex.sub(lambda x: "[~accountid:%s]" % self.USERS.get(
                    x.groups()[0], x.groups()[0]), args['<comment>']),
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
    @docoptwrapper
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
    @docoptwrapper
    def transition(self, line=''):
        TRANSITIONS = {
            'open': 'Open',
            'dev': '81',
            'testing': '31',
            'qa': '211', # Waiting for QA
            'start':  '11', # Start Development
            'analysis': '261',
            'wontfix': '271',
        }
        args = docopt(
            """transition issue to %s
            Usage:
                assign <id> <transition> <comment>
            """ % TRANSITIONS,
            argv=shlex.split(line)
        )
        print((
            self.jira.transition_issue(
                self.jira.issue(args['<id>']),
                TRANSITIONS[args['<transition>']],
                comment=args.get('<comment>'),
            ),
            self.jira.add_comment(
                self.jira.issue(args['<id>']),
                args['<comment>'],
            )
        ))

    @line_magic
    @docoptwrapper
    def label(self, line=''):
        args = docopt(
            """label issue with list of labels eg: sdk,performance
            Usage:
                label <id> <labels>
            """,
            argv=shlex.split(line)
        )
        i0 = self.jira.issue(args['<id>'])
        i0.fields.labels.extend(args['<labels>'].split(','))
        print(
            i0.update(fields={'labels': i0.fields.labels}))

    @line_magic
    @docoptwrapper
    def add_to_epic(self, line=''):
        args = docopt(
            """add list of issues to epic
            Usage:
                label <epicid> <ids> ...
            """,
            argv=shlex.split(line)
        )
        print(self.jira.add_issues_to_epic(args['<epicid>'], args['<ids>']))

    @line_magic
    @docoptwrapper
    def add_to_sprint(self, line=""):
        args = docopt(
            """add list of issues to sprint
            Usage:
                label <sprint> <ids> ...

            <sprint>    Can be a sprint id or name or literal 'current' for current sprint
            """,
            argv=shlex.split(line)
        )
        sprint = args['<sprint>']
        if sprint == 'current':
            sprint = self._current_sprint().id
        elif sprint.isnumeric():
            sprint = int(sprint)
        else:
            for board in self.boards.values():
                for sprintname, sprintdata in board.items():
                    if sprintname == sprint:
                        sprint = sprintdata.id
                        print("Sprint name:%s id:%s" % (sprintname, sprint))
                        break
        print(self.jira.add_issues_to_sprint(sprint, args['<ids>']))
