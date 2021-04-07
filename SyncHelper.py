# pylint: disable=import-error
from DatabaseHelper import Database
from MonicaHelper import Monica
from GoogleHelper import Google
from logging import Logger
from datetime import datetime
from typing import Tuple, Union
import sys

class Sync():
    def __init__(self, log: Logger, monicaHandler: Monica, googleHandler: Google, 
                databaseHandler: Database, syncBackToGoogle: bool) -> None:
        self.log = log
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler
        self.mapping = self.database.getIdMapping()
        self.syncBack = syncBackToGoogle
        self.fakeNum = 1

    def initialSync(self):
        conflicts = []
        contactCount = len(self.google.getContacts())
        msg = "Building sync database..."
        self.log.info(msg)
        print(msg)
        for num, contact in enumerate(self.google.getContacts()):
            sys.stdout.write(f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()
            monicaId = self.mapping.get(contact['resourceName'], None)
            if not monicaId:
                monicaId = self.__simpleMonicaIdSearch(contact)
            if not monicaId:
                conflicts.append(contact)
        if len(conflicts):
            msg = f"Found {len(conflicts)} possible conflicts, starting resolving procedure..."
            self.log.info(msg)
            print("\n"+msg)
        for contact in conflicts:
            monicaId = self.__interactiveMonicaIdSearch(contact)
            assert monicaId, "Could not create a Monica contact. Sync aborted."
        
        if self.syncBack:
            contactCount = len(self.monica.getContacts())
            for num, monicaContact in enumerate(self.monica.getContacts()):
                sys.stdout.write(f"\rProcessing Monica contact {num+1} of {contactCount}")
                sys.stdout.flush()
                if str(monicaContact['id']) not in self.mapping.values():
                    #googleContact = self.google.createContactFromMonicaContact(monicaContact)
                    #gContactDisplayName = googleContact['names'][0]['displayName']
                    # DUMMY! REMOVE LATER!
                    googleContact = self.google.getContacts()[0]
                    googleContact['resourceName'] = self.__generateFakeId(self.mapping.keys())
                    gContactDisplayName = "New contact"
                    # DUMMY! REMOVE LATER!
                    # Update database and mapping
                    self.database.insertData(googleContact['resourceName'],
                                            monicaContact['id'],
                                            gContactDisplayName, 
                                            monicaContact['complete_name'],
                                            googleContact['metadata']['sources'][0]["updateTime"],
                                            monicaContact['updated_at'])
                    msg = f"Sync back: New google contact '{googleContact['resourceName']}' created"
                    print("\n" + msg)
                    self.log.info(msg)
                    self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
                    msg = f"New sync connection between id:'{googleContact['resourceName']}' and id:'{monicaContact['id']}' added"
                    self.log.info(msg)


        msg = "Sync database built!"
        self.log.info(msg)
        print("\n" + msg)

    def __generateFakeId(self, idList: list) -> str:
        '''Used to generate useless ids for debugging and testing'''
        while "fake_" + str(self.fakeNum) in idList:
            self.fakeNum += 1
        return "fake_" + str(self.fakeNum)

    def __convertGoogleTimestamp(self, timestamp: str) -> datetime:
        '''Converts Google timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')

    def __convertMonicaTimestamp(self, timestamp: str) -> datetime:
        '''Converts Monica timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

    def __interactiveMonicaIdSearch(self, googleContact: dict) -> str:
        '''Searches for possible matching candidates and asks for user decision if neccessary.'''
        resolved = False
        candidates = []
        gContactGivenName = googleContact['names'][0].get("givenName", False)
        gContactFamilyName = googleContact['names'][0].get("familyName", False)
        gContactDisplayName = googleContact['names'][0]['displayName']
        monicaContact = None
        for mContact in self.monica.getContacts():
            if str(mContact['id']) not in self.mapping.values():
                if gContactGivenName == mContact['first_name']:
                    candidates.append(mContact)
                elif gContactFamilyName == mContact['last_name']:
                    candidates.append(mContact)
        if candidates:
            print("\nPossible syncing conflict, please choose your alternative by number:")
            print(f"\tWhich Monica contact should be connected to '{gContactDisplayName}'?")
            for num, mContact in enumerate(candidates):
                print(f"\t{num}: {mContact['complete_name']}")
            print(f"\t{num+1}: Create a new Monica contact")
            choice = int(input("Enter your choice (number only): "))
            candidates = candidates[choice:choice+1]
        if not candidates:
            # Create a new Monica contact if chosen or no candidates found
            #monicaContact = self.monica.createContactFromGoogleContact(googleContact)
            # DUMMY! REMOVE LATER!
            monicaContact = self.monica.getContacts()[0]
            monicaContact['id'] = self.__generateFakeId(self.mapping.values())
            monicaContact['complete_name'] = "New contact"
            # DUMMY! REMOVE LATER!
            msg = f"Conflict resolved: New Monica contact with id '{monicaContact['id']}' created for '{gContactDisplayName}'"
            self.log.info(msg)
            print(msg)
            resolved = True
        else:
            monicaContact = candidates[0]
        # Update database and mapping
        self.database.insertData(googleContact['resourceName'],
                                monicaContact['id'], 
                                gContactDisplayName,
                                monicaContact['complete_name'],
                                googleContact['metadata']['sources'][0]["updateTime"],
                                monicaContact['updated_at'])
        self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
        msg = f"New sync connection between id:'{googleContact['resourceName']}' and id:'{monicaContact['id']}' added"
        self.log.info(msg)
        if not resolved: 
            print("Conflict resolved: " + msg)
        return str(monicaContact['id'])


    # pylint: disable=unsubscriptable-object
    def __simpleMonicaIdSearch(self, googleContact: dict) -> Union[str,None]:
        gContactGivenName = googleContact['names'][0].get("givenName", False)
        gContactFamilyName = googleContact['names'][0].get("familyName", False)
        gContactDisplayName = googleContact['names'][0]['displayName']
        candidates = []
        for monicaContact in self.monica.getContacts():
            if str(monicaContact['id']) not in self.mapping.values():
                if gContactDisplayName == monicaContact['complete_name']:
                    candidates.append(monicaContact)
                elif (gContactGivenName and gContactFamilyName and 
                    ' '.join([gContactGivenName, gContactFamilyName]) == monicaContact['complete_name']):
                    candidates.append(monicaContact)
        if len(candidates) == 1:
            monicaContact = candidates[0]
            try:
                self.database.insertData(googleContact['resourceName'],
                                        monicaContact['id'], 
                                        googleContact['names'][0]["displayName"],
                                        monicaContact['complete_name'],
                                        googleContact['metadata']['sources'][0]["updateTime"],
                                        monicaContact['updated_at'])
                self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
                return str(monicaContact['id'])
            except Exception as e:
                self.log.error(f'Error updating database: {str(e)}')
                return None
        return None

    def __getMonicaNamesFromGoogleContact(self, googleContact: dict) -> Tuple[str,str]:
        givenName = googleContact['names'][0].get("givenName", '')
        familyName = googleContact['names'][0].get("familyName", '')
        prefix = googleContact['names'][0].get("honorificPrefix", '')
        suffix = googleContact['names'][0].get("honorificSuffix", '')
        if prefix:
            givenName = prefix + ' ' + givenName
        if suffix:
            familyName = familyName + ' ' + suffix
        return givenName, familyName
