import requests
from logging import Logger
from typing import List, Tuple
from DatabaseHelper import Database
import sys

class Monica():
    '''Handles all Monica related (api) stuff.'''
    def __init__(self, log: Logger, token: str, base_url: str, createReminders: bool, databaseHandler: Database, sampleData: list = None) -> None:
        self.log = log
        self.database = databaseHandler
        self.base_url = base_url
        self.header = {'Authorization': f'Bearer {token}'}
        self.parameters = {'limit': 100}
        self.dataAlreadyFetched = False
        self.contacts = []
        self.updatedContacts = []
        self.createdContacts = []
        self.createReminders = createReminders

        # Debugging area :-)
        self.sampleData = sampleData

    def updateContact(self, id: str, data: dict) -> None:
        '''Updates a given contact and its id via api call.'''
        name = f"{data['first_name']} {data['last_name']}"

        # Update contact
        response = requests.put(self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters, json=data)

        # If successful
        if response.status_code == 200:
            contact = response.json()['data']
            self.updatedContacts.append(contact)
            self.contacts.append(contact)
            self.log.info(f"Contact with name '{name}' and id '{id}' updated successfully")
            self.database.update(monicaId=id, monicaLastChanged=contact['updated_at'], monicaFullName=contact["complete_name"])
        else:
            error = response.json()['error']['message']
            self.log.info(f"Error updating contact '{name}' with id '{id}': {error}")
            raise Exception("Error updating contact!")

    def createContact(self, data: dict) -> dict:
        '''Creates a given contact via api call and returns the created contact.'''
        name = f"{data['first_name']} {data['last_name']}"

        # Create contact
        response = requests.post(self.base_url + f"/contacts", headers=self.header, params=self.parameters, json=data)
        
        # If successful
        if response.status_code == 201:
            contact = response.json()['data']
            self.createdContacts.append(contact)
            self.contacts.append(contact)
            self.log.info(f"Contact with name '{name}' and id '{id}' created successfully")
            return contact
        else:
            error = response.json()['error']['message']
            self.log.info(f"Error creating contact '{name}' with id '{id}': {error}")
            raise Exception("Error creating contact!")

    def getContacts(self) -> list:
        '''Fetches all contacts from Monica if not already fetched.'''
        # Return sample data if present (debugging)
        if self.sampleData:
            return self.sampleData

        # Avoid multiple fetches
        if self.dataAlreadyFetched:
            return self.contacts

        # Start fetching
        maxPage = '?'
        page = 1
        self.log.info("Fetching all Monica contacts...")
        while True:
            sys.stdout.write(f"\rFetching all Monica contacts (page {page} of {maxPage})")
            sys.stdout.flush()
            response = requests.get(self.base_url + f"/contacts?page={page}", headers=self.header, params=self.parameters)
            data = response.json()
            self.contacts += data['data']
            maxPage = data['meta']['last_page']
            if page == maxPage:
                break
            page += 1
        self.dataAlreadyFetched = True
        msg = "Finished fetching Monica contacts"
        self.log.info(msg)
        print("\n" + msg)
        return self.contacts
        

    def getContact(self, id: str) -> dict:
        '''Fetches a single contact by id from Monica.'''
        # Check if contact is already fetched
        if self.contacts:
            monicaContactList = [c for c in self.contacts if str(c['id']) == id]
            if monicaContactList:
                monicaContact = monicaContactList[0]
                # Remove Monica contact from contact list (add again after updated)
                self.contacts.remove(monicaContact)
                return monicaContact

        # Fetch contact
        response = requests.get(self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters)
        
        # If successful
        if response.status_code == 200:
            monicaContact = response.json()['data']
            return monicaContact
        else:
            error = response.json()['error']['message']
            self.log.info(f"Error fetching contact with id '{id}': {error}")
            raise Exception("Error fetching contact!")

class ContactUploadForm():
    '''Creates json form for creating or updating contacts.'''
    def __init__(self, firstName: str, lastName: str = None, nickName: str = None,
                    middleName: str = None, genderType: str = 'O', birthdateDay: str = None,
                    birthdateMonth: str = None, birthdateYear: str = None,
                    birthdateAgeBased: bool = None, isBirthdateKnown: bool = False,
                    isDeceased: bool = False, isDeceasedDateKnown: bool = False,
                    deceasedDay: int = None, deceasedMonth: int = None,
                    deceasedYear: int = None, deceasedAgeBased: bool = None,
                    createReminders: bool = True) -> None:
        genderId = {'M':1, 'F':2, 'O':3}.get(genderType, 3)
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

