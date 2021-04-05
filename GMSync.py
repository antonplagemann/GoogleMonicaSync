VERSION = "v0.1"
# Google-Monica-Sync
# Make sure you installed all requirements using 'pip install -r requirements.txt'

import pickle
import os.path
import requests
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import logging
from conf import TOKEN, BASE_URL

# Global constants
SCOPES = ['https://www.googleapis.com/auth/contacts']
PARAMETERS = {'limit': 100}
HEADER = {'Authorization': f'Bearer {TOKEN}'}

def getGService():
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
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=56411)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('people', 'v1', credentials=creds)
    return service

def getGConnections(service):
    # List contacts
    fields = 'addresses,ageRanges,biographies,birthdays,calendarUrls,clientData,coverPhotos,emailAddresses,events,externalIds,genders,imClients,interests,locales,locations,memberships,metadata,miscKeywords,names,nicknames,occupations,organizations,phoneNumbers,photos,relations,sipAddresses,skills,urls,userDefined'
    results = service.people().connections().list(
        resourceName='people/me',
        pageSize=1000,
        personFields=fields).execute()
    connections = results.get('connections', [])
    return connections

def getGNotes(service):
    # List contacts
    fields = 'biographies,names,userDefined'
    results = service.people().connections().list(
        resourceName='people/me',
        pageSize=1000,
        personFields=fields).execute()
    connections = results.get('connections', [])

    data = {}
    for person in connections:
        names = person.get('names', [])
        biographies = person.get('biographies', [])
        if biographies:
            name = names[0].get('displayName')
            note = biographies[0].get('value')
            if len(biographies) > 1:
                print("alert")
            data.update({name: note})
    return data

def getAllMContacts():
    contacts = []
    page = 1
    while True:
        response = requests.get(BASE_URL + f"/contacts?page={page}", headers=HEADER, params=PARAMETERS)
        data = response.json()
        contacts += data['data']
        maxPage = data['meta']['last_page']
        if page == maxPage:
            break
        page += 1
    return contacts

def getMNotes(contact_id):
    response = requests.get(BASE_URL + f"/contacts/:{contact_id}/notes", headers=HEADER, params=PARAMETERS)
    return response.json()

def setMNote(contact_id, body, isFavorited=False):
    data = {
        "body": body,
        "contact_id": contact_id,
        "is_favorited": int(isFavorited)
    }
    response = requests.post(BASE_URL + "/notes", headers=HEADER, params=PARAMETERS, json=data)
    return response

def getMIds(contacts):
    ids = {}
    for contact in contacts:
        ids.update({contact.get('complete_name'): contact.get('id')})
    return ids

def main():
    try:
        # Get module specific logger
        log = logging.getLogger('GMSync')
        log.setLevel(logging.INFO)
        
        # Logging configuration
        format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler = logging.FileHandler(filename='SyncingLog.log', mode='a', encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(format)
        log.addHandler(handler)
        log.info(f"Sync started")

        # More code

    except Exception as e:
        log.error(str(e))
        log.info("Sync ended\n")
        sys.exit(1)

if __name__ == '__main__':
    main()