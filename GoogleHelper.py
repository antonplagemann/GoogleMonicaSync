import os.path
import pickle
import sys
from logging import Logger
from typing import List, Tuple, Union
import time

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from DatabaseHelper import Database


class Google():
    '''Handles all Google related (api) stuff.'''

    def __init__(self, log: Logger, databaseHandler: Database = None, 
                 labelFilter: dict = None) -> None:
        self.log = log
        self.labelFilter = labelFilter or {"include": [], "exclude": []}
        self.database = databaseHandler
        self.apiRequests = 0
        self.service = self.__buildService()
        self.labelMapping = self.__getLabelMapping()
        self.reverseLabelMapping = {labelId: name for name, labelId in self.labelMapping.items()}
        self.contacts = []
        self.dataAlreadyFetched = False
        self.createdContacts = {}
        self.syncFields = 'addresses,biographies,birthdays,emailAddresses,genders,' \
                          'memberships,metadata,names,nicknames,occupations,organizations,phoneNumbers'
        self.updateFields = 'addresses,biographies,birthdays,clientData,emailAddresses,' \
                            'events,externalIds,genders,imClients,interests,locales,locations,memberships,' \
                            'miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,relations,' \
                            'sipAddresses,urls,userDefined'

    def __buildService(self) -> Resource:
        creds = None
        FILENAME = 'data/token.pickle'
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(FILENAME):
            with open(FILENAME, 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'data/credentials.json', scopes='https://www.googleapis.com/auth/contacts')
                creds = flow.run_local_server(port=56411)
            # Save the credentials for the next run
            with open(FILENAME, 'wb') as token:
                pickle.dump(creds, token)

        service = build('people', 'v1', credentials=creds)
        return service

    def getLabelId(self, name:str, createOnError:bool = True) -> str:
        '''Returns the Google label id for a given tag name.
        Creates a new label if it has not been found.'''
        if createOnError:
            return self.labelMapping.get(name, self.createLabel(name))
        else:
            return self.labelMapping.get(name, '')

    def getLabelName(self, labelString: str) -> str:
        '''Returns the Google label name for a given label id.'''
        labelId = labelString.split("/")[1]
        return self.reverseLabelMapping.get(labelString, labelId)

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

    def __filterUnnamedContacts(self, contactList: List[dict]) -> List[dict]:
        '''Exclude contacts without name.'''
        filteredContactList = []
        for googleContact in contactList:
            # Look for empty names but keep deleted contacts (they too don't have a name)
            isDeleted = googleContact.get('metadata', {}).get('deleted', False)
            isAnyName = any(self.getContactNames(googleContact))
            isNameKeyPresent = googleContact.get('names', False)
            if (not isAnyName or not isNameKeyPresent) and not isDeleted:
                self.log.info(f"Skipped the following unnamed google contact during sync:")
                self.log.info(f"Contact details:\n{self.getContactAsString(googleContact)[2:-1]}")
            else:
                filteredContactList.append(googleContact)
        if len(filteredContactList) != len(contactList):
            print("\nSkipped one or more unnamed google contacts, see log for details")

        return filteredContactList

    def getContactNames(self, googleContact: dict) -> Tuple[str, str, str, str, str, str]:
        '''Returns the given, family and display name of a Google contact.'''
        names = googleContact.get('names', [{}])[0]
        givenName = names.get("givenName", '')
        familyName = names.get("familyName", '')
        displayName = names.get("displayName", '')
        middleName = names.get("middleName", '')
        prefix = names.get("honorificPrefix", '')
        suffix = names.get("honorificSuffix", '')
        nickname = googleContact.get('nicknames', [{}])[0].get('value', '')
        return givenName, middleName, familyName, displayName, prefix, suffix, nickname

    def getContactAsString(self, googleContact: dict) -> str:
        '''Get some content from a Google contact to identify it as a user and return it as string.'''
        string = f"\n\nContact id:\t{googleContact['resourceName']}\n"
        for obj in googleContact.get('names', []):
            for key, value in obj.items():
                if key == 'displayName':
                    string += f"Display name:\t{value}\n"
        for obj in googleContact.get('birthdays', []):
            for key, value in obj.items():
                if key == 'value':
                    string += f"Birthday:\t{value}\n"
        for obj in googleContact.get('organizations', []):
            for key, value in obj.items():
                if key == 'name':
                    string += f"Company:\t{value}\n"
                if key == 'department':
                    string += f"Department:\t{value}\n"
                if key == 'title':
                    string += f"Job title:\t{value}\n"
        for obj in googleContact.get('addresses', []):
            for key, value in obj.items():
                if key == 'formattedValue':
                    value = value.replace('\n', ' ')
                    string += f"Address:\t{value}\n"
        for obj in googleContact.get('phoneNumbers', []):
            for key, value in obj.items():
                if key == 'value':
                    string += f"Phone number:\t{value}\n"
        for obj in googleContact.get('emailAddresses', []):
            for key, value in obj.items():
                if key == 'value':
                    string += f"Email:\t\t{value}\n"
        labels = []
        for obj in googleContact.get('memberships', []):
            for key, value in obj.items():
                if key == 'contactGroupMembership':
                    name = self.getLabelName(value['contactGroupResourceName'])
                    labels.append(name)
        if labels:        
            string += f"Labels:\t\t{', '.join(labels)}\n"
        return string

    def removeContactFromList(self, googleContact: dict) -> None:
        '''Removes a Google contact internally to avoid further processing
        (e.g. if it has been deleted on both sides)'''
        self.contacts.remove(googleContact)

    def getContact(self, googleId: str) -> dict:
        '''Fetches a single contact by id from Google.'''
        try:
            # Check if contact is already fetched
            if self.contacts:
                googleContactList = [c for c in self.contacts if str(c['resourceName']) == str(googleId)]
                if googleContactList: 
                    return googleContactList[0]

            # Build GET parameters
            parameters = {
                'resourceName': googleId,
                'personFields': self.syncFields,
            }

            # Fetch contact
            # pylint: disable=no-member
            result = self.service.people().get(**parameters).execute()
            self.apiRequests += 1

            # Return contact
            googleContact = self.__filterContactsByLabel([result])[0]
            googleContact = self.__filterUnnamedContacts([result])[0]
            self.contacts.append(googleContact)
            return googleContact

        except HttpError as error:
            if self.__isSlowDownError(error):
                return self.getContact(googleId)
            else:
                msg = f"Failed to fetch Google contact '{googleId}': {str(error)}"
                self.log.error(msg)
                raise Exception(msg) from error

        except IndexError as error:
            msg = f"Contact processing of '{googleId}' not allowed by label filter"
            self.log.info(msg)
            raise Exception(msg) from error

        except Exception as error:
            msg = f"Failed to fetch Google contact '{googleId}': {str(error)}"
            self.log.error(msg)
            raise Exception(msg) from error

    def __isSlowDownError(self, error: HttpError) -> bool:
        '''Checks if the error is an qoate exceeded error and slows down the requests if yes.'''
        WAITING_TIME = 60
        if "Quota exceeded" in str(error):
            print(f"\nToo many Google requests, waiting {WAITING_TIME} seconds...")
            time.sleep(WAITING_TIME)
            return True
        else:
            return False

    def getContacts(self, refetchData : bool = False, **params) -> List[dict]:
        '''Fetches all contacts from Google if not already fetched.'''
        # Build GET parameters
        parameters = {'resourceName': 'people/me',
                      'pageSize': 1000,
                      'personFields': self.syncFields,
                      'requestSyncToken': True,
                      **params}

        # Avoid multiple fetches
        if self.dataAlreadyFetched and not refetchData:
            return self.contacts

        # Start fetching
        msg = "Fetching Google contacts..."
        self.log.info(msg)
        sys.stdout.write(f"\r{msg}")
        sys.stdout.flush()
        try:
            self.__fetchContacts(parameters)
        except HttpError as error:
            if 'Sync token' in str(error):
                msg = "Sync token expired or invalid. Fetching again without token (full sync)..."
                self.log.warning(msg)
                print("\n" + msg)
                parameters.pop('syncToken')
                self.__fetchContacts(parameters)
            elif self.__isSlowDownError(error):
                return self.getContacts(refetchData, **params)
            else:
                msg = "Failed to fetch Google contacts!"
                self.log.error(msg)
                raise Exception(str(error)) from error
        msg = "Finished fetching Google contacts"
        self.log.info(msg)
        print("\n" + msg)
        self.dataAlreadyFetched = True
        return self.contacts

    def __fetchContacts(self, parameters: dict) -> None:
        contacts = []
        while True:
            # pylint: disable=no-member
            result = self.service.people().connections().list(**parameters).execute()
            self.apiRequests += 1
            nextPageToken = result.get('nextPageToken', False)
            contacts += result.get('connections', [])
            if nextPageToken:
                parameters['pageToken'] = nextPageToken
            else:
                self.contacts = self.__filterContactsByLabel(contacts)
                self.contacts = self.__filterUnnamedContacts(contacts)
                break

        nextSyncToken = result.get('nextSyncToken', None)
        if nextSyncToken and self.database:
            self.database.updateGoogleNextSyncToken(nextSyncToken)

    def __getLabelMapping(self) -> dict:
        '''Fetches all contact groups from Google (aka labels) and
        returns a {name: id} mapping.'''
        try:
            # Get all contact groups
            # pylint: disable=no-member
            response = self.service.contactGroups().list().execute()
            self.apiRequests += 1
            groups = response.get('contactGroups', [])

            # Initialize mapping for all user groups and allowed system groups
            labelMapping = {group['name']: group['resourceName'] for group in groups
                            if group['groupType'] == 'USER_CONTACT_GROUP'
                            or group['name'] in ['myContacts', 'starred']}

            return labelMapping
        except HttpError as error:
            if self.__isSlowDownError(error):
                return self.__getLabelMapping()
            else:
                msg = "Failed to fetch Google labels!"
                self.log.error(msg)
                raise Exception(str(error)) from error

    def deleteLabel(self, groupId) -> None:
        '''Deletes a contact group from Google (aka label). Does not delete assigned contacts.'''
        try:
            # pylint: disable=no-member
            response = self.service.contactGroups().delete(resourceName=groupId).execute()
            self.apiRequests += 1
        except HttpError as error:
            if self.__isSlowDownError(error):
                self.deleteLabel(groupId)
            else:
                reason = str(error)
                msg = f"Failed to delete Google contact group. Reason: {reason}"
                self.log.warning(msg)
                print("\n" + msg)
                raise Exception(reason) from error

        if response:
            msg = f"Non-empty response received, please check carefully: {response}"
            self.log.warning(msg)
            print("\n" + msg)

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

        try:
            # Upload group object
            # pylint: disable=no-member
            response = self.service.contactGroups().create(body=newGroup).execute()
            self.apiRequests += 1

            groupId = response.get('resourceName', 'contactGroups/myContacts')
            self.labelMapping.update({labelName: groupId})
            return groupId

        except HttpError as error:
            if self.__isSlowDownError(error):
                return self.createLabel(labelName)
            else:
                msg = "Failed to create Google label!"
                self.log.error(msg)
                raise Exception(str(error)) from error

    def createContact(self, data) -> Union[dict, None]:
        '''Creates a given Google contact via api call and returns the created contact.'''
        # Upload contact
        try:
            # pylint: disable=no-member
            result = self.service.people().createContact(personFields=self.syncFields, body=data).execute()
            self.apiRequests += 1
        except HttpError as error:
            if self.__isSlowDownError(error):
                return self.createContact(data)
            else:
                reason = str(error)
                msg = f"'{data['names'][0]}':Failed to create Google contact. Reason: {reason}"
                self.log.error(msg)
                print("\n" + msg)
                raise Exception(reason) from error

        # Process result
        googleId = result.get('resourceName', '-')
        name = result.get('names', [{}])[0].get('displayName', 'error')
        self.createdContacts[googleId] = True
        self.contacts.append(result)
        self.log.info(
            f"'{name}': Contact with id '{googleId}' created successfully")
        return result

    def updateContact(self, data) -> Union[dict, None]:
        '''Updates a given Google contact via api call and returns the created contact.'''
        # Upload contact
        try:
            # pylint: disable=no-member
            result = self.service.people().updateContact(resourceName=data['resourceName'], updatePersonFields=self.updateFields, body=data).execute()
            self.apiRequests += 1
        except HttpError as error:
            if self.__isSlowDownError(error):
                return self.updateContact(data)
            else:
                reason = str(error)
                msg = f"'{data['names'][0]}':Failed to update Google contact. Reason: {reason}"
                self.log.warning(msg)
                print("\n" + msg)
                raise Exception(reason) from error

        # Process result
        googleId = result.get('resourceName', '-')
        name = result.get('names', [{}])[0].get('displayName', 'error')
        self.log.info('Contact has not been saved internally!')
        self.log.info(
            f"'{name}': Contact with id '{googleId}' updated successfully")
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

    def getData(self) -> dict:
        '''Returns the Google contact form data.'''
        return self.data
