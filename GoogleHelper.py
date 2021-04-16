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

    def __init__(self, log: Logger, databaseHandler: Database, labelFilter: dict, sampleData: list = None) -> None:
        self.log = log
        self.labelFilter = labelFilter
        self.database = databaseHandler
        self.service = self.__buildService()
        self.labelMapping = self.__getLabelMapping()
        self.reversedLabelMapping = {id: name for name, id in self.labelMapping.items()}
        self.contacts = []
        self.dataAlreadyFetched = False
        self.updatedContacts = []
        self.createdContacts = []
        self.syncFields = 'addresses,ageRanges,biographies,birthdays,calendarUrls,clientData,coverPhotos,emailAddresses,events,externalIds,genders,imClients,interests,locales,locations,memberships,metadata,miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,photos,relations,sipAddresses,skills,urls,userDefined'

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

    def __filterContactsByLabel(self, contactList: List[dict]) -> List[dict]:
        '''Filters a contact list by include/exclude labels.'''
        if self.labelFilter["include"]:
            return [contact for contact in contactList
                    if any([contactLabel["contactGroupMembership"]["contactGroupId"] 
                            in self.labelFilter["include"] 
                            for contactLabel in contact["memberships"]])
                    and all([contactLabel["contactGroupMembership"]["contactGroupId"] 
                            not in self.labelFilter["exclude"] 
                            for contactLabel in contact["memberships"]])]
        elif self.labelFilter["exclude"]:
            return [contact for contact in contactList
                    if all([contactLabel["contactGroupMembership"]["contactGroupId"] 
                            not in self.labelFilter["exclude"] 
                            for contactLabel in contact["memberships"]])]
        else:
            return contactList

    def removeContactFromList(self, googleContact: dict) -> None:
        '''Removes a Google contact internally to avoid further processing 
        (e.g. if it has been deleted on both sides)'''
        self.contacts.remove(googleContact)

    def getContacts(self, refetchData: bool = False, **params) -> List[dict]:
        '''Fetches all contacts from Google if not already fetched.'''
        # Build GET parameters
        parameters = {'resourceName': 'people/me',
                      'pageSize': 1000,
                      'personFields': self.syncFields,
                      **params}

        # Return sample data if present (debugging)
        if self.sampleData:
            return self.sampleData

        # Avoid multiple fetches
        if self.dataAlreadyFetched and not refetchData:
            return self.contacts

        # Start fetching
        contacts = []
        msg = "Fetching Google contacts..."
        self.log.info(msg)
        sys.stdout.write(f"\r{msg}")
        sys.stdout.flush()
        try:
            while True:
                # pylint: disable=no-member
                result = self.service.people().connections().list(**parameters).execute()
                nextPageToken = result.get('nextPageToken', False)
                contacts += result.get('connections', [])
                if nextPageToken:
                    parameters['pageToken'] = nextPageToken
                else:
                    self.contacts = self.__filterContactsByLabel(contacts)
                    break
        except HttpError as error:
            if 'Sync token' in error._get_reason():
                msg = "Sync token expired or invalid. Fetching again without token (full sync)..."
                self.log.warning(msg)
                print("\n" + msg)
                parameters.pop('syncToken')
                contacts = []
                while True:
                    # pylint: disable=no-member
                    result = self.service.people().connections().list(**parameters).execute()
                    nextPageToken = result.get('nextPageToken', False)
                    contacts += result.get('connections', [])
                    if nextPageToken:
                        parameters['pageToken'] = nextPageToken
                    else:
                        self.contacts = self.__filterContactsByLabel(contacts)
                        break
            else:
                raise Exception(error._get_reason())
        nextSyncToken = result.get('nextSyncToken', None)
        if nextSyncToken:
            self.database.updateGoogleNextSyncToken(nextSyncToken)
        msg = "Finished fetching Google contacts"
        self.log.info(msg)
        print("\n" + msg)
        self.dataAlreadyFetched = True
        return self.contacts

    def __getLabelMapping(self) -> dict:
        '''Fetches all contact groups from Google (aka labels) and
        returns a {name: id} mapping.'''
        # Get all contact groups
        # pylint: disable=no-member
        response = self.service.contactGroups().list().execute()
        groups = response.get('contactGroups', [])

        # Initialize mapping for all user groups and allowed system groups
        labelMapping = {group['name']: group['resourceName'] for group in groups
                        if group['groupType'] == 'USER_CONTACT_GROUP'
                        or group['name'] in ['myContacts', 'starred']}

        return labelMapping

    def createLabel(self, labelName: str) -> str:
        '''Creates a new Google contacts label and returns its id.'''
        # Search label and return if found
        if labelName in self.labelMapping:
            return self.labelMapping[labelName]

        # Create group object
        newGroup = {
            "contactGroup": {
                "name": labelName
            }
        }

        # Upload group object
        # pylint: disable=no-member
        response = self.service.contactGroups().create(body=newGroup).execute()
        groupId = response.get('resourceName', 'contactGroups/myContacts')
        self.labelMapping.update({labelName: groupId})
        return groupId

    def createContact(self, data) -> dict:
        '''Creates a given Google contact via api call and returns the created contact.'''
        # Upload contact
        try:
            # pylint: disable=no-member
            result = self.service.people().createContact(
                personFields=self.syncFields, body=data).execute()
        except HttpError as error:
            reason = error._get_reason()
            msg = f"'{data['names'][0]}':Failed to create Google contact. Reason: {reason}"
            self.log.warning(msg)
            print("\n" + msg)
            return

        # Process result
        id = result.get('resourceName', '-')
        name = result.get('names', [{}])[0].get('displayName', 'error')
        self.createdContacts.append(result)
        self.contacts.append(result)
        self.log.info(
            f"'{name}': Contact with id '{id}' created successfully")
        return result


class GoogleContactUploadForm():
    '''Creates json form for creating Google contacts.'''

    def __init__(self, firstName: str = '', lastName: str = '',
                 middleName: str = '', birthdate: dict = {},
                 phoneNumbers: List[str] = [], career: dict = {},
                 emailAdresses: List[str] = [], labelIds: List[str] = [],
                 addresses: List[dict] = {}) -> None:
        self.data = {
            "names": [
                {
                    "familyName": lastName,
                    "givenName": firstName,
                    "middleName": middleName
                }
            ]
        }

        if birthdate:
            self.data["birthdays"] = [
                {
                    "date": {
                        "year": birthdate.get('year', 0),
                        "month": birthdate.get('month', 0),
                        "day": birthdate.get('day', 0)
                    }
                }
            ]

        if career:
            self.data["organizations"] = [
                {
                    "name": career.get('company', ''),
                    "title": career.get('job', '')
                }
            ]

        if addresses:
            self.data["addresses"] = [
                {
                    'type': address.get("name",''),
                    "streetAddress": address.get('street', ''),
                    "city": address.get('city', ''),
                    "region": address.get('province', ''),
                    "postalCode": address.get('postal_code', ''),
                    "country": address["country"].get("name", None) if address["country"] else None,
                    "countryCode": address["country"].get("iso", None) if address["country"] else None,
                }
                for address in addresses
            ]

        if phoneNumbers:
            self.data["phoneNumbers"] = [
                {
                    "value": number,
                    "type": "other",
                }
                for number in phoneNumbers
            ]

        if emailAdresses:
            self.data["emailAddresses"] = [
                {
                    "value": email,
                    "type": "other",
                }
                for email in emailAdresses
            ]

        if labelIds:
            self.data["memberships"] = [
                {
                    "contactGroupMembership":
                    {
                        "contactGroupResourceName": labelId
                    }
                }
                for labelId in labelIds
            ]
