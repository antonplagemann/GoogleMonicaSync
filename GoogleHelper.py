import pickle
import os.path
from googleapiclient.discovery import build, Resource
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from logging import Logger
from typing import List
from DatabaseHelper import Database

class Google():
    '''Handles all Google related (api) stuff.'''
    def __init__(self, log: Logger, databaseHandler: Database, sampleData: list = None) -> None:
        self.log = log
        self.database = databaseHandler
        self.service = self.__buildService()
        self.contacts = sampleData
        self.updatedContacts = []
        self.createdContacts = []

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

    def getContacts(self) -> List[dict]:
        '''Fetches all contacts from Google if not already fetched.'''
        if not self.contacts:
            # Contact fields to be retrieved
            fields = 'addresses,ageRanges,biographies,birthdays,calendarUrls,clientData,coverPhotos,emailAddresses,events,externalIds,genders,imClients,interests,locales,locations,memberships,metadata,miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,photos,relations,sipAddresses,skills,urls,userDefined'
            # pylint: disable=no-member
            results = self.service.people().connections().list(
                resourceName='people/me',
                pageSize=1000,
                personFields=fields).execute()
            self.contacts = results.get('connections', [])
            return self.contacts
        return self.contacts