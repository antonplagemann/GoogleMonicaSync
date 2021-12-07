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
from Exceptions import GoogleFetchError, InternalError


class Google():
    '''Handles all Google related (api) stuff.'''

    def __init__(self, log: Logger, database_handler: Database = None,
                 label_filter: dict = None) -> None:
        self.log = log
        self.label_filter = label_filter or {"include": [], "exclude": []}
        self.database = database_handler
        self.api_requests = 0
        self.service = self.__build_service()
        self.label_mapping = self.__get_label_mapping()
        self.reverse_label_mapping = {
            label_id: name for name, label_id in self.label_mapping.items()}
        self.contacts = []
        self.data_already_fetched = False
        self.created_contacts = {}
        self.sync_fields = 'addresses,biographies,birthdays,emailAddresses,genders,' \
            'memberships,metadata,names,nicknames,occupations,organizations,phoneNumbers'
        self.update_fields = 'addresses,biographies,birthdays,clientData,emailAddresses,' \
            'events,externalIds,genders,imClients,interests,locales,locations,memberships,' \
            'miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,relations,' \
            'sipAddresses,urls,userDefined'

    def __build_service(self) -> Resource:
        creds = None
        FILENAME = 'token.pickle'
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
                    'credentials.json', scopes='https://www.googleapis.com/auth/contacts')
                creds = flow.run_local_server(port=56411)
            # Save the credentials for the next run
            with open(FILENAME, 'wb') as token:
                pickle.dump(creds, token)

        service = build('people', 'v1', credentials=creds)
        return service

    def get_label_id(self, name: str, create_on_error: bool = True) -> str:
        '''Returns the Google label id for a given tag name.
        Creates a new label if it has not been found.'''
        if create_on_error:
            return self.label_mapping.get(name, self.create_label(name))
        else:
            return self.label_mapping.get(name, '')

    def get_label_name(self, label_string: str) -> str:
        '''Returns the Google label name for a given label id.'''
        label_id = label_string.split("/")[1]
        return self.reverse_label_mapping.get(label_string, label_id)

    def __filter_contacts_by_label(self, contact_list: List[dict]) -> List[dict]:
        '''Filters a contact list by include/exclude labels.'''
        if self.label_filter["include"]:
            return [contact for contact in contact_list
                    if any([contact_label["contactGroupMembership"]["contactGroupId"]
                            in self.label_filter["include"]
                            for contact_label in contact["memberships"]])
                    and all([contact_label["contactGroupMembership"]["contactGroupId"]
                            not in self.label_filter["exclude"]
                            for contact_label in contact["memberships"]])]
        elif self.label_filter["exclude"]:
            return [contact for contact in contact_list
                    if all([contact_label["contactGroupMembership"]["contactGroupId"]
                            not in self.label_filter["exclude"]
                            for contact_label in contact["memberships"]])]
        else:
            return contact_list

    def __filter_unnamed_contacts(self, contact_list: List[dict]) -> List[dict]:
        '''Exclude contacts without name.'''
        filtered_contact_list = []
        for google_contact in contact_list:
            # Look for empty names but keep deleted contacts (they too don't have a name)
            is_deleted = google_contact.get(
                'metadata', {}).get('deleted', False)
            is_any_name = any(self.get_contact_names(google_contact))
            is_name_key_present = google_contact.get('names', False)
            if (not is_any_name or not is_name_key_present) and not is_deleted:
                self.log.info(
                    "Skipped the following unnamed google contact during sync:")
                self.log.info(
                    f"Contact details:\n{self.get_contact_as_string(google_contact)[2:-1]}")
            else:
                filtered_contact_list.append(google_contact)
        if len(filtered_contact_list) != len(contact_list):
            print("\nSkipped one or more unnamed google contacts, see log for details")

        return filtered_contact_list

    def get_contact_names(self, google_contact: dict) -> Tuple[str, str, str, str, str, str]:
        '''Returns the given, family and display name of a Google contact.'''
        names = google_contact.get('names', [{}])[0]
        given_name = names.get("givenName", '')
        family_name = names.get("familyName", '')
        display_name = names.get("displayName", '')
        middle_name = names.get("middleName", '')
        prefix = names.get("honorificPrefix", '')
        suffix = names.get("honorificSuffix", '')
        nickname = google_contact.get('nicknames', [{}])[0].get('value', '')
        return given_name, middle_name, family_name, display_name, prefix, suffix, nickname

    def get_contact_as_string(self, google_contact: dict) -> str:
        '''Get some content from a Google contact to identify it as a user
        and return it as string.'''
        search_keys = {
            'names': ['displayName'],
            'birthdays': ['value'],
            'organizations': ['name', 'department', 'title'],
            'addresses': ['formattedValue'],
            'phoneNumbers': ['value'],
            'emailAddresses': ['value'],
            'memberships': ['contactGroupMembership']
        }

        contact_string = f"\n\nContact id: {google_contact['resourceName']}\n"

        for key, values in google_contact.items():
            if key not in search_keys:
                continue
            sub_string = ""
            for value in values:
                for sub_key, sub_value in value.items():
                    if sub_key not in search_keys[key]:
                        continue
                    if sub_key == 'contactGroupMembership':
                        sub_value = self.get_label_name(sub_value['contactGroupResourceName'])
                    sub_value = sub_value.replace('\n', ' ')
                    sub_string += f"  {sub_key}: {sub_value}\n"
            if sub_string:
                contact_string += f"{key}:\n" + sub_string

        return contact_string

    def remove_contact_from_list(self, google_contact: dict) -> None:
        '''Removes a Google contact internally to avoid further processing
        (e.g. if it has been deleted on both sides)'''
        self.contacts.remove(google_contact)

    def get_contact(self, google_id: str) -> dict:
        '''Fetches a single contact by id from Google.'''
        try:
            # Check if contact is already fetched
            if self.contacts:
                google_contact_list = [c for c in self.contacts if str(
                    c['resourceName']) == str(google_id)]
                if google_contact_list:
                    return google_contact_list[0]

            # Build GET parameters
            parameters = {
                'resourceName': google_id,
                'personFields': self.sync_fields,
            }

            # Fetch contact
            result = self.service.people().get(**parameters).execute()
            self.api_requests += 1

            # Return contact
            google_contact = self.__filter_contacts_by_label([result])[0]
            google_contact = self.__filter_unnamed_contacts([result])[0]
            self.contacts.append(google_contact)
            return google_contact

        except HttpError as error:
            if self.__is_slow_down_error(error):
                return self.get_contact(google_id)
            else:
                msg = f"Failed to fetch Google contact '{google_id}': {str(error)}"
                self.log.error(msg)
                raise GoogleFetchError(msg) from error

        except IndexError as error:
            msg = f"Contact processing of '{google_id}' not allowed by label filter"
            self.log.info(msg)
            raise InternalError(msg) from error

        except Exception as error:
            msg = f"Failed to fetch Google contact '{google_id}': {str(error)}"
            self.log.error(msg)
            raise GoogleFetchError(msg) from error

    def __is_slow_down_error(self, error: HttpError) -> bool:
        '''Checks if the error is an quota exceeded error and slows down the requests if yes.'''
        WAITING_TIME = 60
        if "Quota exceeded" in str(error):
            print(
                f"\nToo many Google requests, waiting {WAITING_TIME} seconds...")
            time.sleep(WAITING_TIME)
            return True
        else:
            return False

    def get_contacts(self, refetch_data: bool = False, **params) -> List[dict]:
        '''Fetches all contacts from Google if not already fetched.'''
        # Build GET parameters
        parameters = {'resourceName': 'people/me',
                      'pageSize': 1000,
                      'personFields': self.sync_fields,
                      'requestSyncToken': True,
                      **params}

        # Avoid multiple fetches
        if self.data_already_fetched and not refetch_data:
            return self.contacts

        # Start fetching
        msg = "Fetching Google contacts..."
        self.log.info(msg)
        sys.stdout.write(f"\r{msg}")
        sys.stdout.flush()
        try:
            self.__fetch_contacts(parameters)
        except HttpError as error:
            if 'Sync token' in str(error):
                msg = "Sync token expired or invalid. Fetching again without token (full sync)..."
                self.log.warning(msg)
                print("\n" + msg)
                parameters.pop('syncToken')
                self.__fetch_contacts(parameters)
            elif self.__is_slow_down_error(error):
                return self.get_contacts(refetch_data, **params)
            else:
                msg = "Failed to fetch Google contacts!"
                self.log.error(msg)
                raise GoogleFetchError(str(error)) from error
        msg = "Finished fetching Google contacts"
        self.log.info(msg)
        print("\n" + msg)
        self.data_already_fetched = True
        return self.contacts

    def __fetch_contacts(self, parameters: dict) -> None:
        contacts = []
        while True:
            result = self.service.people().connections().list(**parameters).execute()
            self.api_requests += 1
            next_page_token = result.get('nextPageToken', False)
            contacts += result.get('connections', [])
            if next_page_token:
                parameters['pageToken'] = next_page_token
            else:
                self.contacts = self.__filter_contacts_by_label(contacts)
                self.contacts = self.__filter_unnamed_contacts(contacts)
                break

        next_sync_token = result.get('nextSyncToken', None)
        if next_sync_token and self.database:
            self.database.update_google_next_sync_token(next_sync_token)

    def __get_label_mapping(self) -> dict:
        '''Fetches all contact groups from Google (aka labels) and
        returns a {name: id} mapping.'''
        try:
            # Get all contact groups
            response = self.service.contactGroups().list().execute()
            self.api_requests += 1
            groups = response.get('contactGroups', [])

            # Initialize mapping for all user groups and allowed system groups
            label_mapping = {group['name']: group['resourceName'] for group in groups
                             if group['groupType'] == 'USER_CONTACT_GROUP'
                             or group['name'] in ['myContacts', 'starred']}

            return label_mapping
        except HttpError as error:
            if self.__is_slow_down_error(error):
                return self.__get_label_mapping()
            else:
                msg = "Failed to fetch Google labels!"
                self.log.error(msg)
                raise GoogleFetchError(str(error)) from error

    def delete_label(self, group_id) -> None:
        '''Deletes a contact group from Google (aka label). Does not delete assigned contacts.'''
        try:
            response = self.service.contactGroups().delete(resourceName=group_id).execute()
            self.api_requests += 1
        except HttpError as error:
            if self.__is_slow_down_error(error):
                self.delete_label(group_id)
            else:
                reason = str(error)
                msg = f"Failed to delete Google contact group. Reason: {reason}"
                self.log.warning(msg)
                print("\n" + msg)
                raise GoogleFetchError(reason) from error

        if response:
            msg = f"Non-empty response received, please check carefully: {response}"
            self.log.warning(msg)
            print("\n" + msg)

    def create_label(self, label_name: str) -> str:
        '''Creates a new Google contacts label and returns its id.'''
        # Search label and return if found
        if label_name in self.label_mapping:
            return self.label_mapping[label_name]

        # Create group object
        new_group = {
            "contactGroup": {
                "name": label_name
            }
        }

        try:
            # Upload group object
            response = self.service.contactGroups().create(body=new_group).execute()
            self.api_requests += 1

            group_id = response.get('resourceName', 'contactGroups/myContacts')
            self.label_mapping.update({label_name: group_id})
            return group_id

        except HttpError as error:
            if self.__is_slow_down_error(error):
                return self.create_label(label_name)
            else:
                msg = "Failed to create Google label!"
                self.log.error(msg)
                raise GoogleFetchError(str(error)) from error

    def create_contact(self, data) -> Union[dict, None]:
        '''Creates a given Google contact via api call and returns the created contact.'''
        # Upload contact
        try:
            result = self.service.people().createContact(
                personFields=self.sync_fields, body=data).execute()
            self.api_requests += 1
        except HttpError as error:
            if self.__is_slow_down_error(error):
                return self.create_contact(data)
            else:
                reason = str(error)
                msg = f"'{data['names'][0]}':Failed to create Google contact. Reason: {reason}"
                self.log.error(msg)
                print("\n" + msg)
                raise GoogleFetchError(reason) from error

        # Process result
        google_id = result.get('resourceName', '-')
        name = result.get('names', [{}])[0].get('displayName', 'error')
        self.created_contacts[google_id] = True
        self.contacts.append(result)
        self.log.info(
            f"'{name}': Contact with id '{google_id}' created successfully")
        return result

    def update_contact(self, data) -> Union[dict, None]:
        '''Updates a given Google contact via api call and returns the created contact.'''
        # Upload contact
        try:
            result = self.service.people().updateContact(
                resourceName=data['resourceName'],
                updatePersonFields=self.update_fields, body=data).execute()
            self.api_requests += 1
        except HttpError as error:
            if self.__is_slow_down_error(error):
                return self.update_contact(data)
            else:
                reason = str(error)
                msg = f"'{data['names'][0]}':Failed to update Google contact. Reason: {reason}"
                self.log.warning(msg)
                print("\n" + msg)
                raise GoogleFetchError(reason) from error

        # Process result
        google_id = result.get('resourceName', '-')
        name = result.get('names', [{}])[0].get('displayName', 'error')
        self.log.info('Contact has not been saved internally!')
        self.log.info(
            f"'{name}': Contact with id '{google_id}' updated successfully")
        return result


class GoogleContactUploadForm():
    '''Creates json form for creating Google contacts.'''

    def __init__(self, first_name: str = '', last_name: str = '',
                 middle_name: str = '', birthdate: dict = {},
                 phone_numbers: List[str] = [], career: dict = {},
                 email_adresses: List[str] = [], label_ids: List[str] = [],
                 addresses: List[dict] = {}) -> None:
        self.data = {
            "names": [
                {
                    "familyName": last_name,
                    "givenName": first_name,
                    "middleName": middle_name
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
                    'type': address.get("name", ''),
                    "streetAddress": address.get('street', ''),
                    "city": address.get('city', ''),
                    "region": address.get('province', ''),
                    "postalCode": address.get('postal_code', ''),
                    "country": address["country"].get("name", None) if address["country"] else None,
                    "countryCode": address["country"].get("iso", None) if address["country"] else None,
                }
                for address in addresses
            ]

        if phone_numbers:
            self.data["phoneNumbers"] = [
                {
                    "value": number,
                    "type": "other",
                }
                for number in phone_numbers
            ]

        if email_adresses:
            self.data["emailAddresses"] = [
                {
                    "value": email,
                    "type": "other",
                }
                for email in email_adresses
            ]

        if label_ids:
            self.data["memberships"] = [
                {
                    "contactGroupMembership":
                    {
                        "contactGroupResourceName": label_id
                    }
                }
                for label_id in label_ids
            ]

    def get_data(self) -> dict:
        '''Returns the Google contact form data.'''
        return self.data
