import http.client
import logging
import re
from functools import cached_property

import click
import keyring
from indico_cli import cli as indico_cli

from .gsuite import GSuite


class ContextObject:
    def __init__(self, env, debug=False):
        self.debug = debug
        self.indico_env = env

        if debug:
            level = logging.DEBUG
            logging.basicConfig()
            logging.getLogger().setLevel(level)
            requests_log = logging.getLogger("requests.packages.urllib3")
            requests_log.setLevel(level)
            requests_log.propagate = True

            if level == logging.DEBUG:
                http.client.HTTPConnection.debuglevel = 1

    @cached_property
    def indico(self):
        return indico_cli.init_indico(self.indico_env)

    @cached_property
    def gsuite(self):
        return GSuite()


@click.group()
@click.option("--debug", is_flag=True, help="Enable debugging.")
@click.option(
    "--env",
    default="prod",
    type=click.Choice(("prod", "stage", "local")),
    help="Indico environment to use.",
)
@click.pass_context
def main(ctx, debug, env):
    ctx.obj = ContextObject(env, debug)


@main.command()
@click.pass_obj
def cleartoken(ctxo):
    """Clear GSuite tokens."""

    try:
        ctxo.gsuite.clear_credentials()
        click.echo("Successfully cleared auth token")
    except keyring.errors.PasswordDeleteError:
        pass


@main.group(help="Commands related to GSuite.")
@click.pass_context
def gsuite(ctx):
    ctx.obj = ctx.parent.obj.gsuite


@gsuite.command()
@click.argument("sheetfile")
@click.argument("sheetname", required=False)
@click.pass_obj
def sheetcsv(gsuite, sheetfile, sheetname):
    """Export a Google Sheet as CSV.

    Pass either the id of the file, or its URL. If you pass an URL with gid included, it will take
    the exact sheet you are on. Otherwise, you can pass the sheet name in addition.
    """

    if sheetfile.startswith("http"):
        match = re.search(
            r"^https://docs.google.com/spreadsheets/d/([^/]*)/edit(?:#gid=(\d+))?",
            sheetfile,
        )
        if not match:
            raise click.BadParameter("Invalid Sheets URL")
        sheetfile = match[1]
        if not sheetname:
            sheetname = match[2]

    click.echo(gsuite.sheetcsv(sheetfile, sheetname), nl=False)


@gsuite.command()
@click.argument("calendar_name")
@click.argument("event_ids", nargs=-1)
@click.option(
    "-f",
    "--file",
    "attfile",
    required=True,
    type=click.File(),
    help="The file to read attendees from",
)
@click.option("--notify/--no-notify", default=True, help="Send event notifications")
@click.pass_obj
def attendees(gsuite, calendar_name, event_ids, attfile, notify, attendees):
    """Set attendees for one or more events.

    Pass the name of the calendar as noted on calendar.google.com, and any number of event ids. You
    can get the event ids using the list-events function.
    """

    attendees = attfile.read().rstrip().splitlines()

    calendar_id = gsuite.calendar_by_name(calendar_name)
    if not calendar_id:
        raise click.BadParameter("Unknown calendar name")

    for event_id in event_ids:
        event = gsuite.set_event_attendees(
            calendar_id, event_id, attendees, notify=notify
        )
        attlen = len(event["attendees"]) if "attendees" in event else 0
        click.echo(f"Updated event '{event['summary']}' with {attlen} attendees")


@gsuite.command()
@click.argument("calendar_name")
@click.option(
    "-s",
    "--start",
    "time_min",
    type=click.DateTime(),
    help="Start of range to query in",
)
@click.option(
    "-e", "--end", "time_max", type=click.DateTime(), help="End of range to query in"
)
@click.option("-q", "--query", help="Query string to search for (e.g. full title)")
@click.pass_obj
def list_events(gsuite, calendar_name, time_min, time_max, query):
    """List events from a calendar using specific criteria.

    Pass the name of the calendar as noted on calendar.google.com and use the options to filter. The
    query option is highly recommended.
    """

    calendar_id = gsuite.calendar_by_name(calendar_name)
    if not calendar_id:
        raise click.BadParameter("Unknown calendar name")

    events = gsuite.list_events(calendar_id, time_min, time_max, query)
    if not events:
        click.echo("No events found.")
    else:
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            click.echo(f"{event['id']} - {event['summary']} ({start} to {end})")


@main.group(help="Commands related to indico.")
@click.pass_context
def indico(ctx):
    ctx.obj = ctx.parent.obj.indico


for name, command in indico_cli.main.commands.items():
    indico.add_command(command)


if __name__ == "__main__":
    main(prog_name="eatool")
