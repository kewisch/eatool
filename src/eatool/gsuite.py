import csv
import io
import json
from functools import cached_property

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Not committing this file right now, it should ideally be part of a config.
from .oauth import OAUTH_CREDS

class GSuite:

    SCOPES = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    @cached_property
    def calsvc(self):
        creds = self.get_credentials()
        return build("calendar", "v3", credentials=creds)

    @cached_property
    def sheetsvc(self):
        creds = self.get_credentials()
        return build("sheets", "v4", credentials=creds)

    def clear_credentials(self):
        keyring.delete_password("eatool", "gsuite")

    def get_credentials(self):
        creds = None

        tokendata = keyring.get_password("eatool", "gsuite")
        if tokendata:
            creds = Credentials.from_authorized_user_info(info=json.loads(tokendata))

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    OAUTH_CREDS, scopes=GSuite.SCOPES
                )
                creds = flow.run_local_server(port=0)

            keyring.set_password("eatool", "gsuite", creds.to_json())

        return creds

    def set_event_attendees(self, calendar_id, event_id, attendees, notify=True):
        event = (
            self.calsvc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        )
        event["attendees"] = [{"email": email} for email in attendees]
        sendUpdates = "all" if notify else "none"
        return (
            self.calsvc.events()
            .update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendUpdates=sendUpdates,
            )
            .execute()
        )

    def list_events(self, calendar_id, time_min=None, time_max=None, query=None):
        events_result = (
            self.calsvc.events()
            .list(
                calendarId=calendar_id,
                q=query,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return events_result.get("items", [])

    def sheetcsv(self, file_id, sheetName=None):
        sheet_metadata = (
            self.sheetsvc.spreadsheets().get(spreadsheetId=file_id).execute()
        )

        if sheetName and sheetName.isdigit():
            # Assume this is a gid
            sheets = sheet_metadata.get("sheets", [])
            sheetName = int(sheetName)

            for sheet in sheets:
                if sheet["properties"]["sheetId"] == sheetName:
                    sheetName = sheet["properties"]["title"]
            if not sheetName:
                raise Exception("Could not find sheet " + sheetName)

        elif not sheetName:
            try:
                sheetName = sheet_metadata["sheets"][0]["properties"]["title"]
            except KeyError:
                sheetName = "Sheet1"

        sheet = (
            self.sheetsvc.spreadsheets()
            .values()
            .get(spreadsheetId=file_id, range=sheetName)
            .execute()
        )
        rows = filter(None, sheet.get("values", []))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()

    def calendar_by_name(self, name):
        calendar_list = self.calsvc.calendarList().list().execute()

        for entry in calendar_list["items"]:
            if entry["summary"] == name:
                return entry["id"]

        return None
