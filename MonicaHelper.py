import requests
from logging import Logger
from typing import List

class Monica():
    def __init__(self, log: Logger, token: str, base_url: str, sampleData: list = None) -> None:
        self.log = log
        self.base_url = base_url
        self.header = {'Authorization': f'Bearer {token}'}
        self.parameters = {'limit': 100}
        self.contacts = sampleData

    def getNotes(self, contact_id: str):
        response = requests.get(self.base_url + f"/contacts/:{contact_id}/notes", headers=self.header, params=self.parameters)
        return response.json()

    def setNote(self, contact_id: str, body: str, isFavorited: str = False):
        data = {
            "body": body,
            "contact_id": contact_id,
            "is_favorited": int(isFavorited)
        }
        response = requests.post(self.base_url + "/notes", headers=self.header, params=self.parameters, json=data)
        return response

    def getContacts(self):
        if not self.contacts:
            self.contacts = []
            page = 1
            while True:
                response = requests.get(self.base_url + f"/contacts?page={page}", headers=self.header, params=self.parameters)
                data = response.json()
                self.contacts += data['data']
                maxPage = data['meta']['last_page']
                if page == maxPage:
                    break
                page += 1
            return self.contacts
        return self.contacts
    
    def createContactFromGoogleContact(self, googleContact: dict) -> None:
        raise NotImplementedError

    def createContact(self) -> None:
        raise NotImplementedError



