import requests
from logging import Logger
from typing import List, Tuple
from DatabaseHelper import Database
import sys


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
        self.updatedContacts = []
        self.createdContacts = []
        self.createReminders = createReminders

        # Debugging area :-)
        self.sampleData = sampleData

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

    def updateContact(self, id: str, data: dict) -> None:
        '''Updates a given contact and its id via api call.'''
        name = f"{data['first_name']} {data['last_name']}"

        # Remove Monica contact from contact list (add again after updated)
        self.contacts = [c for c in self.contacts if str(c['id']) != str(id)]

        # Update contact
        response = requests.put(self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 200:
            contact = response.json()['data']
            self.updatedContacts.append(contact)
            self.contacts.append(contact)
            name = contact["complete_name"]
            self.log.info(f"'{name}' ('{id}'): Contact updated successfully")
            self.database.update(
                monicaId=id, monicaLastChanged=contact['updated_at'], monicaFullName=contact["complete_name"])
        else:
            error = response.json()['error']['message']
            self.log.error(f"'{name}' ('{id}'): Error updating Monica contact: {error}. Does it exist?")
            raise Exception("Error updating Monica contact!")

    def deleteContact(self, id: str, name: str) -> None:
        '''Deletes the contact with the given id from Monica and removes it from the internal list.'''

        # Delete contact
        response = requests.delete(
            self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters)

        # If successful
        if response.status_code == 200:
            self.contacts = [c for c in self.contacts if str(c['id']) != str(id)]
        else:
            error = response.json()['error']['message']
            self.log.error(f"'{name}' ('{id}'): Failed to complete delete request: {error}")
            raise Exception("Error deleting Monica contact!")

    def createContact(self, data: dict) -> dict:
        '''Creates a given Monica contact via api call and returns the created contact.'''
        name = f"{data['first_name']} {data['last_name']}"

        # Create contact
        response = requests.post(self.base_url + f"/contacts",
                                 headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 201:
            contact = response.json()['data']
            self.createdContacts.append(contact)
            self.contacts.append(contact)
            self.log.info(f"'{name}' ('{contact['id']}'): Contact created successfully")
            return contact
        else:
            error = response.json()['error']['message']
            self.log.info(f"'{name}': Error creating Monica contact: {error}")
            raise Exception("Error creating Monica contact!")

    def getContacts(self) -> list:
        '''Fetches all contacts from Monica if not already fetched.'''
        try:
            # Return sample data if present (debugging)
            if self.sampleData:
                return self.sampleData

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

    def getContact(self, id: str) -> dict:
        '''Fetches a single contact by id from Monica.'''
        try:
            # Check if contact is already fetched
            if self.contacts:
                monicaContactList = [c for c in self.contacts if str(c['id']) == str(id)]
                if monicaContactList: 
                    return monicaContactList[0]

            # Fetch contact
            response = requests.get(
                self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters)

            # If successful
            if response.status_code == 200:
                monicaContact = response.json()['data']
                self.contacts.append(monicaContact)
                return monicaContact
            else:
                error = response.json()['error']['message']
                msg = f"Error fetching Monica contact '{id}': {error}"
                self.log.error(msg)
                raise Exception(msg)

        except Exception as e:
            msg = f"Failed to fetch Monica contact (maybe connection issue): {str(e)}"
            print("\n" + msg)
            self.log.error(msg)
            raise Exception(msg)

    def getNotes(self, monicaId: str, name: str) -> List[dict]:
        '''Fetches all contact notes for a given Monica contact id via api call.'''

        # Get contact fields
        response = requests.get(self.base_url + f"/contacts/{monicaId}/notes", headers=self.header, params=self.parameters)

        # If successful
        if response.status_code == 200:
            monicaNotes = response.json()['data']
            return monicaNotes
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error fetching Monica notes: {error}")

    def addNote(self, data: dict, name: str) -> None:
        '''Creates a new note for a given contact id via api call.'''
        # Initialization
        monicaId = data['contact_id']

        # Create address
        response = requests.post(self.base_url + f"/notes", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 201:
            note = response.json()['data']
            id = note["id"]
            self.log.info(f"'{name}' ('{monicaId}'): Note '{id}' created successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica note: {error}")

    def removeTags(self, data: dict, monicaId: str, name: str) -> None:
        '''Removes all tags given by id from a given contact id via api call.'''

        # Create address
        response = requests.post(self.base_url + f"/contacts/{monicaId}/unsetTag", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 200:
            self.log.info(f"'{name}' ('{monicaId}'): Labels with id {data['tags']} removed successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error removing Monica labels: {error}")

    def addTags(self, data: dict, monicaId: str, name: str) -> None:
        '''Adds all tags given by name for a given contact id via api call.'''

        # Create address
        response = requests.post(self.base_url + f"/contacts/{monicaId}/setTags", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 200:
            self.log.info(f"'{name}' ('{monicaId}'): Labels {data['tags']} assigned successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error assigning Monica labels: {error}")


    def updateCareer(self, id: str, data: dict) -> None:
        '''Updates job title and company for a given contact id via api call.'''
        # Initialization
        contact = self.getContact(id)
        name = contact['complete_name']

        # Update contact
        response = requests.put(self.base_url + f"/contacts/{id}/work", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 200:
            contact = response.json()['data']
            self.log.info(f"'{name}' ('{id}'): Company and job title updated successfully")
            self.database.update(monicaId=id, monicaLastChanged=contact['updated_at'])
        else:
            error = response.json()['error']['message']
            self.log.warning(f"'{name}' ('{id}'): Error updating Monica contact career info: {error}")

    def deleteAddress(self, id: str, monicaId: str, name: str) -> None:
        '''Deletes an address for a given address id via api call.'''
        # Delete address
        response = requests.delete(self.base_url + f"/addresses/{id}", headers=self.header, params=self.parameters)

        # If successful
        if response.status_code == 200:
            self.log.info(f"'{name}' ('{monicaId}'): Address '{id}' deleted successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error deleting address '{id}': {error}")

    def createAddress(self, data: dict, name: str) -> None:
        '''Creates an address for a given contact id via api call.'''
        # Initialization
        monicaId = data['contact_id']

        # Create address
        response = requests.post(self.base_url + f"/addresses", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 201:
            address = response.json()['data']
            id = address["id"]
            self.log.info(f"'{name}' ('{monicaId}'): Address '{id}' created successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica address: {error}")

    def getContactFields(self, monicaId: str, name: str) -> List[dict]:
        '''Fetches all contact fields (phone numbers, emails, etc.) 
        for a given Monica contact id via api call.'''

        # Get contact fields
        response = requests.get(self.base_url + f"/contacts/{monicaId}/contactfields", headers=self.header, params=self.parameters)

        # If successful
        if response.status_code == 200:
            fieldList = response.json()['data']
            return fieldList
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error fetching Monica contact fields: {error}")

    def createContactField(self, monicaId: str, data: dict, name: str) -> None:
        '''Creates a contact field (phone number, email, etc.) 
        for a given Monica contact id via api call.'''

        # Create contact field
        response = requests.post(self.base_url + f"/contactfields", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 201:
            contactField = response.json()['data']
            fieldId = contactField["id"]
            typeDesc = contactField["contact_field_type"]["type"]
            self.log.info(f"'{name}' ('{monicaId}'): Contact field '{fieldId}' ({typeDesc}) created successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error creating Monica contact field: {error}")

    def deleteContactField(self, fieldId: str, monicaId: str, name: str) -> None:
        '''Updates a contact field (phone number, email, etc.) 
        for a given Monica contact id via api call.'''

        # Delete contact field
        response = requests.delete(self.base_url + f"/contactfields/{fieldId}", headers=self.header, params=self.parameters)

        # If successful
        if response.status_code == 200:
            self.log.info(f"'{name}' ('{monicaId}'): Contact field '{fieldId}' deleted successfully")
        else:
            error = response.json()['error']['message']
            raise Exception(f"'{name}' ('{monicaId}'): Error deleting Monica contact field '{fieldId}': {error}")


class MonicaContactUploadForm():
    '''Creates json form for creating or updating Monica contacts.'''

    def __init__(self, firstName: str, lastName: str = None, nickName: str = None,
                 middleName: str = None, genderType: str = 'O', birthdateDay: str = None,
                 birthdateMonth: str = None, birthdateYear: str = None,
                 birthdateAgeBased: bool = None, isBirthdateKnown: bool = False,
                 isDeceased: bool = False, isDeceasedDateKnown: bool = False,
                 deceasedDay: int = None, deceasedMonth: int = None,
                 deceasedYear: int = None, deceasedAgeBased: bool = None,
                 createReminders: bool = True) -> None:
        genderId = {'M': 1, 'F': 2, 'O': 3}.get(genderType, 3)
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
