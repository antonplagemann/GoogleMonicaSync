import pickle
import os.path
from googleapiclient.discovery import build, Resource
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from logging import Logger
from typing import List
from DatabaseHelper import Database
import sys

class Google():
    '''Handles all Google related (api) stuff.'''
    def __init__(self, log: Logger, databaseHandler: Database, sampleData: list = None) -> None:
        self.log = log
        self.database = databaseHandler
        self.service = self.__buildService()
        self.contacts = []
        self.dataAlreadyFetched = False
        self.updatedContacts = []
        self.createdContacts = []

        # Debugging area :-)
        self.sampleData = sampleData

    def __buildService(self) -> Resource:
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', scopes='https://www.googleapis.com/auth/contacts')
                creds = flow.run_local_server(port=56411)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('people', 'v1', credentials=creds)
        return service

    def removeContactFromList(self, googleContact: dict) -> None:
        '''Removes a Google contact internally to avoid further processing 
        (e.g. if it has been deleted on both sides)'''
        self.contacts.remove(googleContact)

    def getContacts(self, refetchData: bool = False, **params) -> List[dict]:
        '''Fetches all contacts from Google if not already fetched.'''
        # Build GET parameters
        fields = 'addresses,ageRanges,biographies,birthdays,calendarUrls,clientData,coverPhotos,emailAddresses,events,externalIds,genders,imClients,interests,locales,locations,memberships,metadata,miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,photos,relations,sipAddresses,skills,urls,userDefined'
        parameters = {'resourceName': 'people/me', 
                        'pageSize': 1000, 
                        'personFields': fields, 
                        **params}

        # Return sample data if present (debugging)
        if self.sampleData:
            return self.sampleData

        # Avoid multiple fetches
        if self.dataAlreadyFetched and not refetchData:
            return self.contacts

        # Start fetching
        msg = "Fetching all Google contacts..."
        self.log.info(msg)
        sys.stdout.write(f"\r{msg}")
        sys.stdout.flush()
        try:
            # pylint: disable=no-member
            result = self.service.people().connections().list(**parameters).execute()
        except HttpError as error:
            if 'Sync token' in error._get_reason():
                msg = "Sync token expired or wrong. Fetching again without token (full sync)..."
                self.log.warning(msg)
                print("\n" + msg)
                parameters.pop('syncToken')
                # pylint: disable=no-member
                result = self.service.people().connections().list(**parameters).execute()
            else:
                raise Exception(error._get_reason())
        nextSyncToken = result.get('nextSyncToken', None)
        if nextSyncToken:
            self.database.updateGoogleNextSyncToken(nextSyncToken)
        self.contacts = result.get('connections', [])
        msg = "Finished fetching Google contacts"
        self.log.info(msg)
        print("\n" + msg)
        self.dataAlreadyFetched = True
        return self.contacts
