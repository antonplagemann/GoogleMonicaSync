import requests
from logging import Logger
from typing import List, Tuple
from DatabaseHelper import Database
import sys

class Monica():
    def __init__(self, log: Logger, token: str, base_url: str, databaseHandler: Database, sampleData: list = None) -> None:
        self.log = log
        self.database = databaseHandler
        self.base_url = base_url
        self.header = {'Authorization': f'Bearer {token}'}
        self.parameters = {'limit': 100}
        self.contacts = sampleData
        self.updatedContacts = []
        self.createdContacts = []

    def updateContact(self, id: str, data: dict) -> dict:
        response = requests.put(self.base_url + f"/contacts/{id}", headers=self.header, params=self.parameters, json=data)
        name = f"{data['first_name']} {data['last_name']}"
        if response.status_code == 200:
            contact = response.json()['data']
            self.updatedContacts.append(contact)
            self.log.info(f"Contact with name '{name}' and id '{id}' updated successfully")
            self.database.update(monicaId=id, monicaLastChanged=contact['updated_at'], monicaFullName=contact["complete_name"])
        else:
            error = response.json()['error']['message']
            self.log.info(f"Error updating contact '{name}' with id '{id}': {error}")

    def createContact(self, data: dict) -> dict:
        response = requests.post(self.base_url + f"/contacts", headers=self.header, params=self.parameters, json=data)
        name = f"{data['first_name']} {data['last_name']}"
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

    def getContacts(self):
        if not self.contacts:
            self.contacts = []
            maxPage = '?'
            page = 1
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
            return self.contacts
        return self.contacts

class ContactUploadForm():
    def __init__(self, firstName: str, lastName: str = None, nickName: str = None,
                    middleName: str = None, genderType: str = 'O', birthdateDay: str = None,
                    birthdateMonth: str = None, birthdateYear: str = None,
                    birthdateAgeBased: bool = None, isBirthdateKnown: bool = False,
                    isDeceased: bool = False, isDeceasedDateKnown: bool = False,
                    deceasedDay: int = None, deceasedMonth: int = None,
                    deceasedYear: int = None, deceasedAgeBased: bool = None) -> None:
        genderId = {'M':1, 'W':2, 'O':3}.get(genderType, 3)
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
            "is_birthdate_known": isBirthdateKnown,
            "is_deceased": isDeceased,
            "is_deceased_date_known": isDeceasedDateKnown,
            "deceased_date_day": deceasedDay,
            "deceased_date_month": deceasedMonth,
            "deceased_date_year": deceasedYear,
            "deceased_date_is_age_based": deceasedAgeBased,
        }

