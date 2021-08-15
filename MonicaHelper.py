import sys
from logging import Logger
from typing import List
import time

import requests
from requests.models import Response

from DatabaseHelper import Database


class Monica():
    '''Handles all Monica related (api) stuff.'''

    def __init__(self, log: Logger, databaseHandler: Database, token: str, base_url: str, createReminders: bool, labelFilter: dict, sampleData: list = None) -> None:
        self.log = log
        self.database = databaseHandler
        self.base_url = base_url
        self.labelFilter = labelFilter
        self.header = {'Authorization': f'Bearer {token}'}
        self.parameters = {'limit': 100}
        self.dataAlreadyFetched = False
        self.contacts = []
        self.genderMapping = {}
        self.contactFieldTypeMapping = {}
        self.updatedContacts = {}
        self.createdContacts = {}
        self.deletedContacts = {}
        self.apiRequests = 0
        self.createReminders = createReminders

    def __filterContactsByLabel(self, contactList: List[dict]) -> List[dict]:
        '''Filters a contact list by include/exclude labels.'''
        if self.labelFilter["include"]:
            return [contact for contact in contactList
                    if any([contactLabel["name"]
                            in self.labelFilter["include"] 
                            for contactLabel in contact["tags"]])
                    and all([contactLabel["name"] 
                            not in self.labelFilter["exclude"] 
                            for contactLabel in contact["tags"]])]
        elif self.labelFilter["exclude"]:
            return [contact for contact in contactList
                    if all([contactLabel["name"]
                            not in self.labelFilter["exclude"] 
                            for contactLabel in contact["tags"]])]
        else:
            return contactList

    def updateStatistics(self) -> None:
        '''Updates internal statistics for printing.'''
        # A contact should only count as updated if it has not been created during sync
        self.updatedContacts = {key: value for key, value in self.updatedContacts.items()
                                if key not in self.createdContacts}

    def getGenderMapping(self) -> dict:
        '''Fetches all genders from Monica and saves them to a dictionary.'''
        # Only fetch if not present yet
        if self.genderMapping:
            return self.genderMapping

        while True:
        # Get genders
            response = requests.get(
                self.base_url + f"/genders", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                genders = response.json()['data']
                genderMapping = {gender['type']: gender['id'] for gender in genders}
                self.genderMapping = genderMapping
                return self.genderMapping
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.error(f"Failed to fetch genders from Monica: {error}")
                raise Exception("Error fetching genders from Monica!")

    def updateContact(self, monicaId: str, data: dict) -> None:
        '''Updates a given contact and its id via api call.'''
        name = f"{data['first_name']} {data['last_name']}"

        # Remove Monica contact from contact list (add again after updated)
        self.contacts = [c for c in self.contacts if str(c['id']) != str(monicaId)]

        while True:
            # Update contact
            response = requests.put(self.base_url + f"/contacts/{monicaId}", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                contact = response.json()['data']
                self.updatedContacts[monicaId] = True
                self.contacts.append(contact)
                name = contact["complete_name"]
                self.log.info(f"'{name}' ('{monicaId}'): Contact updated successfully")
                self.database.update(
                    monicaId=monicaId, monicaLastChanged=contact['updated_at'], monicaFullName=contact["complete_name"])
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.error(f"'{name}' ('{monicaId}'): Error updating Monica contact: {error}. Does it exist?")
                self.log.error(f"Monica form data: {data}")
                raise Exception("Error updating Monica contact!")

    def deleteContact(self, monicaId: str, name: str) -> None:
        '''Deletes the contact with the given id from Monica and removes it from the internal list.'''

        while True:
            # Delete contact
            response = requests.delete(
                self.base_url + f"/contacts/{monicaId}", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.contacts = [c for c in self.contacts if str(c['id']) != str(monicaId)]
                self.deletedContacts[monicaId] = True
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.error(f"'{name}' ('{monicaId}'): Failed to complete delete request: {error}")
                raise Exception("Error deleting Monica contact!")

    def createContact(self, data: dict, referenceId: str) -> dict:
        '''Creates a given Monica contact via api call and returns the created contact.'''
        name = f"{data['first_name']} {data['last_name']}".strip()

        while True:
            # Create contact
            response = requests.post(self.base_url + f"/contacts",
                                    headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 201:
                contact = response.json()['data']
                self.createdContacts[contact['id']] = True
                self.contacts.append(contact)
                self.log.info(f"'{referenceId}' ('{contact['id']}'): Contact created successfully")
                return contact
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.info(f"'{referenceId}': Error creating Monica contact: {error}")
                raise Exception("Error creating Monica contact!")

    def getContacts(self) -> List[dict]:
        '''Fetches all contacts from Monica if not already fetched.'''
        try:
            # Avoid multiple fetches
            if self.dataAlreadyFetched:
                return self.contacts

            # Start fetching
            maxPage = '?'
            page = 1
            contacts = []
            self.log.info("Fetching all Monica contacts...")
            while True:
                sys.stdout.write(f"\rFetching all Monica contacts (page {page} of {maxPage})")
                sys.stdout.flush()
                response = requests.get(
                    self.base_url + f"/contacts?page={page}", headers=self.header, params=self.parameters)
                self.apiRequests += 1
                # If successful
                if response.status_code == 200:
                    data = response.json()
                    contacts += data['data']
                    maxPage = data['meta']['last_page']
                    if page == maxPage:
                        self.contacts = self.__filterContactsByLabel(contacts)
                        break
                    page += 1
                else:
                    error = response.json()['error']['message']
                    if self.__isSlowDownError(response, error):
                        continue
                    msg = f"Error fetching Monica contacts: {error}"
                    self.log.error(msg)
                    raise Exception(msg)
            self.dataAlreadyFetched = True
            msg = "Finished fetching Monica contacts"
            self.log.info(msg)
            print("\n" + msg)
            return self.contacts

        except Exception as e:
            msg = f"Failed to fetch Monica contacts (maybe connection issue): {str(e)}"
            print("\n" + msg)
            self.log.error(msg)
            raise Exception(msg)

    def getContact(self, monicaId: str) -> dict:
        '''Fetches a single contact by id from Monica.'''
        try:
            # Check if contact is already fetched
            if self.contacts:
                monicaContactList = [c for c in self.contacts if str(c['id']) == str(monicaId)]
                if monicaContactList: 
                    return monicaContactList[0]

            while True:
                # Fetch contact
                response = requests.get(
                    self.base_url + f"/contacts/{monicaId}", headers=self.header, params=self.parameters)
                self.apiRequests += 1

                # If successful
                if response.status_code == 200:
                    monicaContact = response.json()['data']
                    monicaContact = self.__filterContactsByLabel([monicaContact])[0]
                    self.contacts.append(monicaContact)
                    return monicaContact
                else:
                    error = response.json()['error']['message']
                    if self.__isSlowDownError(response, error):
                        continue
                    raise Exception(error)

        except IndexError:
            msg = f"Contact processing of '{monicaId}' not allowed by label filter"
            self.log.info(msg)
            raise Exception(msg)

        except Exception as e:
            msg = f"Failed to fetch Monica contact '{monicaId}': {str(e)}"
            self.log.error(msg)
            raise Exception(msg)

    def getNotes(self, monicaId: str, name: str) -> List[dict]:
        '''Fetches all contact notes for a given Monica contact id via api call.'''

        while True:
            # Get contact fields
            response = requests.get(self.base_url + f"/contacts/{monicaId}/notes", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                monicaNotes = response.json()['data']
                return monicaNotes
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error fetching Monica notes: {error}")

    def addNote(self, data: dict, name: str) -> None:
        '''Creates a new note for a given contact id via api call.'''
        # Initialization
        monicaId = data['contact_id']

        while True:
            # Create address
            response = requests.post(self.base_url + f"/notes", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 201:
                self.updatedContacts[monicaId] = True
                note = response.json()['data']
                noteId = note["id"]
                self.log.info(f"'{name}' ('{monicaId}'): Note '{noteId}' created successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica note: {error}")

    def updateNote(self, noteId: str, data: dict, name: str) -> None:
        '''Creates a new note for a given contact id via api call.'''
        # Initialization
        monicaId = data['contact_id']

        while True:
            # Create address
            response = requests.put(self.base_url + f"/notes/{noteId}", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                note = response.json()['data']
                noteId = note["id"]
                self.log.info(f"'{name}' ('{monicaId}'): Note '{noteId}' updated successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error updating Monica note: {error}")

    def deleteNote(self, noteId: str, monicaId: str, name: str) -> None:
        '''Creates a new note for a given contact id via api call.'''

        while True:
            # Create address
            response = requests.delete(self.base_url + f"/notes/{noteId}", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                self.log.info(f"'{name}' ('{monicaId}'): Note '{noteId}' deleted successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error deleting Monica note: {error}")

    def removeTags(self, data: dict, monicaId: str, name: str) -> None:
        '''Removes all tags given by id from a given contact id via api call.'''

        while True:
            # Create address
            response = requests.post(self.base_url + f"/contacts/{monicaId}/unsetTag", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                self.log.info(f"'{name}' ('{monicaId}'): Label(s) with id {data['tags']} removed successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error removing Monica labels: {error}")

    def addTags(self, data: dict, monicaId: str, name: str) -> None:
        '''Adds all tags given by name for a given contact id via api call.'''

        while True:
            # Create address
            response = requests.post(self.base_url + f"/contacts/{monicaId}/setTags", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                self.log.info(f"'{name}' ('{monicaId}'): Labels {data['tags']} assigned successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error assigning Monica labels: {error}")


    def updateCareer(self, monicaId: str, data: dict) -> None:
        '''Updates job title and company for a given contact id via api call.'''
        # Initialization
        contact = self.getContact(monicaId)
        name = contact['complete_name']

        while True:
            # Update contact
            response = requests.put(self.base_url + f"/contacts/{monicaId}/work", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                contact = response.json()['data']
                self.log.info(f"'{name}' ('{monicaId}'): Company and job title updated successfully")
                self.database.update(monicaId=monicaId, monicaLastChanged=contact['updated_at'])
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.warning(f"'{name}' ('{monicaId}'): Error updating Monica contact career info: {error}")

    def deleteAddress(self, addressId: str, monicaId: str, name: str) -> None:
        '''Deletes an address for a given address id via api call.'''
        while True:
            # Delete address
            response = requests.delete(self.base_url + f"/addresses/{addressId}", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                self.log.info(f"'{name}' ('{monicaId}'): Address '{addressId}' deleted successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error deleting address '{addressId}': {error}")

    def createAddress(self, data: dict, name: str) -> None:
        '''Creates an address for a given contact id via api call.'''
        # Initialization
        monicaId = data['contact_id']

        while True:
            # Create address
            response = requests.post(self.base_url + f"/addresses", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 201:
                self.updatedContacts[monicaId] = True
                address = response.json()['data']
                addressId = address["id"]
                self.log.info(f"'{name}' ('{monicaId}'): Address '{addressId}' created successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica address: {error}")

    def getContactFields(self, monicaId: str, name: str) -> List[dict]:
        '''Fetches all contact fields (phone numbers, emails, etc.) 
        for a given Monica contact id via api call.'''

        while True:
            # Get contact fields
            response = requests.get(self.base_url + f"/contacts/{monicaId}/contactfields", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                fieldList = response.json()['data']
                return fieldList
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error fetching Monica contact fields: {error}")

    def getContactFieldId(self, typeName: str) -> str:
        '''Returns the id for a Monica contact field.'''
        # Fetch if not present yet
        if not self.contactFieldTypeMapping:
            self.__getContactFieldTypes()

        # Get contact field id
        fieldId = self.contactFieldTypeMapping.get(typeName, None)

        # No id is a serious issue
        if not fieldId:
            raise Exception(f"Could not find an id for contact field type '{typeName}'")

        return fieldId
            
    def __getContactFieldTypes(self) -> dict:
        '''Fetches all contact field types from Monica and saves them to a dictionary.'''

        while True:
        # Get genders
            response = requests.get(
                self.base_url + f"/contactfieldtypes", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                contactFieldTypes = response.json()['data']
                contactFieldTypeMapping = {field['type']: field['id'] for field in contactFieldTypes}
                self.contactFieldTypeMapping = contactFieldTypeMapping
                return self.contactFieldTypeMapping
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                self.log.error(f"Failed to fetch contact field types from Monica: {error}")
                raise Exception("Error fetching contact field types from Monica!")


    def createContactField(self, monicaId: str, data: dict, name: str) -> None:
        '''Creates a contact field (phone number, email, etc.) 
        for a given Monica contact id via api call.'''

        while True:
            # Create contact field
            response = requests.post(self.base_url + f"/contactfields", headers=self.header, params=self.parameters, json=data)
            self.apiRequests += 1

            # If successful
            if response.status_code == 201:
                self.updatedContacts[monicaId] = True
                contactField = response.json()['data']
                fieldId = contactField["id"]
                typeDesc = contactField["contact_field_type"]["type"]
                self.log.info(f"'{name}' ('{monicaId}'): Contact field '{fieldId}' ({typeDesc}) created successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica contact field: {error}")

    def deleteContactField(self, fieldId: str, monicaId: str, name: str) -> None:
        '''Updates a contact field (phone number, email, etc.) 
        for a given Monica contact id via api call.'''

        while True:
            # Delete contact field
            response = requests.delete(self.base_url + f"/contactfields/{fieldId}", headers=self.header, params=self.parameters)
            self.apiRequests += 1

            # If successful
            if response.status_code == 200:
                self.updatedContacts[monicaId] = True
                self.log.info(f"'{name}' ('{monicaId}'): Contact field '{fieldId}' deleted successfully")
                return
            else:
                error = response.json()['error']['message']
                if self.__isSlowDownError(response, error):
                    continue
                raise Exception(f"'{name}' ('{monicaId}'): Error deleting Monica contact field '{fieldId}': {error}")

    def __isSlowDownError(self, response: Response, error: str) -> bool:
        '''Checks if the error is an rate limiter error and slows down the requests if yes.'''
        if "Too many attempts, please slow down the request" in error:
            sec = int(response.headers.get('Retry-After'))
            print(f"\nToo many Monica requests, waiting {sec} seconds...")
            time.sleep(sec)
            return True
        else:
            return False

class MonicaContactUploadForm():
    '''Creates json form for creating or updating Monica contacts.'''

    def __init__(self, monica: Monica, firstName: str, lastName: str = None, nickName: str = None,
                 middleName: str = None, genderType: str = 'O', birthdateDay: str = None,
                 birthdateMonth: str = None, birthdateYear: str = None,
                 birthdateAgeBased: bool = False, isBirthdateKnown: bool = False,
                 isDeceased: bool = False, isDeceasedDateKnown: bool = False,
                 deceasedDay: int = None, deceasedMonth: int = None,
                 deceasedYear: int = None, deceasedAgeBased: bool = None,
                 createReminders: bool = True) -> None:
        genderId = monica.getGenderMapping()[genderType]
        self.data = {
            "first_name": firstName,
            "last_name": lastName,
            "nickname": nickName,
            "middle_name": middleName,
            "gender_id": genderId,
            "birthdate_day": birthdateDay,
            "birthdate_month": birthdateMonth,
            "birthdate_year": birthdateYear,
            "birthdate_is_age_based": birthdateAgeBased,
            "deceased_date_add_reminder": createReminders,
            "birthdate_add_reminder": createReminders,
            "is_birthdate_known": isBirthdateKnown,
            "is_deceased": isDeceased,
            "is_deceased_date_known": isDeceasedDateKnown,
            "deceased_date_day": deceasedDay,
            "deceased_date_month": deceasedMonth,
            "deceased_date_year": deceasedYear,
            "deceased_date_is_age_based": deceasedAgeBased,
        }
