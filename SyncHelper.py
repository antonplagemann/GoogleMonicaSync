# pylint: disable=import-error
from DatabaseHelper import Database
from MonicaHelper import Monica, ContactUploadForm
from GoogleHelper import Google
from logging import Logger
from datetime import datetime
from typing import Tuple, Union
import sys

class Sync():
    '''Handles all syncing and merging issues with Google and Monica and the database.'''
    def __init__(self, log: Logger, monicaHandler: Monica, googleHandler: Google, 
                databaseHandler: Database, syncBackToGoogle: bool) -> None:
        self.log = log
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler
        self.mapping = self.database.getIdMapping()
        self.nextSyncToken = self.database.getGoogleNextSyncToken()
        self.syncBack = syncBackToGoogle

        # Debugging area :-)
        self.fakeNum = 1

    def startSync(self) -> None:
        '''Starts the next sync type depending on database data.'''
        if not self.mapping:
            self.initialSync()
        elif not self.nextSyncToken:
            self.fullSync()
        else:
            self.deltaSync()
        

    def initialSync(self) -> None:
        '''Builds the syncing database and starts a full sync.'''
        self.database.deleteAndInitialize()
        self.mapping.clear()
        self.__buildSyncDatabase()
        self.fullSync(dateBasedSync=False)

    def deltaSync(self) -> None:
        '''Fetches every contact from Google that has changed since the last sync.'''
        self.google.getContacts(requestSyncToken=True, syncToken=self.nextSyncToken)
        #tbc

    def fullSync(self, dateBasedSync: bool = True, requestGoogleSyncToken: bool = True) -> None:
        '''Fetches every contact from Google and Monica and does a full sync.'''
        # Initialization
        contactCount = len(self.google.getContacts(requestSyncToken=requestGoogleSyncToken))
        msg = "Starting full sync..."
        self.log.info(msg)
        print(msg)

        # Process every Google contact
        for num, googleContact in enumerate(self.google.getContacts()):
            sys.stdout.write(f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()

            # Skip all contacts which have not changed according to the database lastChanged date
            if dateBasedSync:
                # Get timestamps
                databaseTimestamp = self.database.findById(googleId=googleContact["resourceName"])[4]
                databaseDate = self.__convertGoogleTimestamp(databaseTimestamp)
                contactTimestamp = googleContact['metadata']['sources'][0]["updateTime"]
                contactDate = self.__convertGoogleTimestamp(contactTimestamp)

                # Skip if nothing has changed
                if databaseDate == contactDate:
                    continue

            # Get Monica id from database (index 1 in returned row)
            monicaId = self.database.findById(googleId=googleContact["resourceName"])[1]
            # Get Monica contact by id
            monicaContact = self.monica.getContact(monicaId)
            
            # Merge and update name, birthday and deceased date
            self.__mergeAndUpdateNBD(monicaContact, googleContact)

        # Finished
        msg = "Full sync finished!"
        self.log.info(msg)
        print("\n" + msg)

    def __buildSyncDatabase(self) -> None:
        '''Builds a Google <-> Monica contact id mapping and saves it to the database.'''
        # Initialization
        conflicts = []
        contactCount = len(self.google.getContacts())
        msg = "Building sync database..."
        self.log.info(msg)
        print(msg)

        # Process every Google contact
        for num, googleContact in enumerate(self.google.getContacts()):
            sys.stdout.write(f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()
            monicaId = self.mapping.get(googleContact['resourceName'], None)
            if not monicaId:
                # If not found in database: try non-interactive search first
                monicaId = self.__simpleMonicaIdSearch(googleContact)
            if not monicaId:
                # Non-interactive search failed, try interactive search next
                conflicts.append(googleContact)

        # Process all conflicts
        if len(conflicts):
            msg = f"Found {len(conflicts)} possible conflicts, starting resolving procedure..."
            self.log.info(msg)
            print("\n" + msg)
        for googleContact in conflicts:
            # Do a interactive search with user interaction next
            monicaId = self.__interactiveMonicaIdSearch(googleContact)
            assert monicaId, "Could not create a Monica contact. Sync aborted."
        
        # Sync lonely Monica contacts back to Google
        if self.syncBack:
            contactCount = len(self.monica.getContacts())

            # Process every Monica contact
            for num, monicaContact in enumerate(self.monica.getContacts()):
                sys.stdout.write(f"\rProcessing Monica contact {num+1} of {contactCount}")
                sys.stdout.flush()

                # If there the id isnt in the database: create a new Google contact and upload
                if str(monicaContact['id']) not in self.mapping.values():
                    # Create Google contact
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

        # Finished
        msg = "Sync database built!"
        self.log.info(msg)
        print("\n" + msg)

    def __generateFakeId(self, idList: list) -> str:
        '''Used to generate useless ids for debugging and testing'''
        while "fake_" + str(self.fakeNum) in idList:
            self.fakeNum += 1
        return "fake_" + str(self.fakeNum)
    
    def __mergeAndUpdateNBD(self, monicaContact: dict, googleContact: dict) -> dict:
        '''Updates names, birthday and deceased date by merging an existing Monica contact with
        a given Google contact.'''
        # Get names
        firstName, lastName = self.__getMonicaNamesFromGoogleContact(googleContact)
        middleName = googleContact['names'][0].get("middleName", '')
        displayName = googleContact['names'][0].get("displayName", '')
        # First name is required for Monica
        if not firstName:
            firstName = displayName 
            lastName = ''

        # Get birthday
        birthday = googleContact.get("birthdays", None)
        birthdateYear, birthdateMonth, birthdateDay = None, None, None
        if birthday:
            birthdateYear = birthday[0].get("date", {}).get("year", None)
            birthdateMonth = birthday[0].get("date", {}).get("month", None)
            birthdateDay = birthday[0].get("date", {}).get("day", None)
        
        # Get deceased info
        deceasedDate = monicaContact["information"]["dates"]["deceased_date"]["date"]
        deceasedDateIsAgeBased = monicaContact["information"]["dates"]["deceased_date"]["is_age_based"]
        deceasedYear, deceasedMonth, deceasedDay = None, None, None
        if deceasedDate:
            date = self.__convertMonicaTimestamp(deceasedDate)
            deceasedYear = date.year
            deceasedMonth = date.month
            deceasedDay = date.day

        # Assemble form object
        form = ContactUploadForm(firstName=firstName, lastName=lastName, nickName=monicaContact["nickname"],
                                        middleName=middleName, genderType=monicaContact["gender_type"],
                                        birthdateDay=birthdateDay, birthdateMonth=birthdateMonth,
                                        birthdateYear=birthdateYear, isBirthdateKnown=bool(birthday),
                                        isDeceased=monicaContact["is_dead"], isDeceasedDateKnown=bool(deceasedDate),
                                        deceasedYear=deceasedYear, deceasedMonth=deceasedMonth,
                                        deceasedDay=deceasedDay, deceasedAgeBased=deceasedDateIsAgeBased,
                                        createReminders=self.monica.createReminders)
        # Upload contact
        self.monica.updateContact(id=monicaContact["id"], data=form.data)

    def __createMonicaContact(self, googleContact: dict) -> dict:
        '''Creates a new Monica contact from a given Google contact.'''
        # Get names
        firstName, lastName = self.__getMonicaNamesFromGoogleContact(googleContact)
        middleName = googleContact['names'][0].get("middleName", '')
        displayName = googleContact['names'][0].get("displayName", '')
        # First name is required for Monica
        if not firstName:
            firstName = displayName 
            lastName = ''

        # Get birthday
        birthday = googleContact.get("birthdays", None)
        birthdateYear, birthdateMonth, birthdateDay = None, None, None
        if birthday:
            birthdateYear = birthday[0].get("date", {}).get("year", None)
            birthdateMonth = birthday[0].get("date", {}).get("month", None)
            birthdateDay = birthday[0].get("date", {}).get("day", None)

        # Assemble form object
        form = ContactUploadForm(firstName=firstName, lastName=lastName, middleName=middleName,
                                        birthdateDay=birthdateDay, birthdateMonth=birthdateMonth,
                                        birthdateYear=birthdateYear, isBirthdateKnown=bool(birthday),
                                        createReminders=self.monica.createReminders)
        # Upload contact
        monicaContact = self.monica.createContact(data=form.data)
        return monicaContact

    def __convertGoogleTimestamp(self, timestamp: str) -> datetime:
        '''Converts Google timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')

    def __convertMonicaTimestamp(self, timestamp: str) -> datetime:
        '''Converts Monica timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

    def __interactiveMonicaIdSearch(self, googleContact: dict) -> str:
        '''Advanced search by first and last name for a given Google contact. 
        Tries to find a matching Monica contact and asks for user choice if 
        at least one candidate has been found. Creates a new Monica contact
        if neccessary or chosen by User. Returns Monica contact id.'''
        # Initialization
        resolved = False
        candidates = []
        gContactGivenName = googleContact['names'][0].get("givenName", False)
        gContactFamilyName = googleContact['names'][0].get("familyName", False)
        gContactDisplayName = googleContact['names'][0]['displayName']
        monicaContact = None

        # Process every Monica contact
        for mContact in self.monica.getContacts():
            if str(mContact['id']) not in self.mapping.values():
                if gContactGivenName == mContact['first_name']:
                    # If the id isnt in the database and first name matches add potential candidate to list
                    candidates.append(mContact)
                elif gContactFamilyName == mContact['last_name']:
                    # If the id isnt in the database and last name matches add potential candidate to list
                    candidates.append(mContact)
        
        # If there is at least one candidate let the user choose
        if candidates:
            print("\nPossible syncing conflict, please choose your alternative by number:")
            print(f"\tWhich Monica contact should be connected to '{gContactDisplayName}'?")
            for num, monicaContact in enumerate(candidates):
                print(f"\t{num}: {monicaContact['complete_name']}")
            print(f"\t{num+1}: Create a new Monica contact")
            choice = int(input("Enter your choice (number only): "))
            # Created a sublist with the selected candidate or an empty list if user votes for a new contact
            candidates = candidates[choice:choice+1]

        # If there are no candidates (user vote or nothing found) create a new Monica contact
        if not candidates:
            # Create a new Monica contact
            monicaContact = self.__createMonicaContact(googleContact)
            # DUMMY! REMOVE LATER!
            #monicaContact = self.monica.getContacts()[0]
            #monicaContact['id'] = self.__generateFakeId(self.mapping.values())
            #monicaContact['complete_name'] = "New contact"
            # DUMMY! REMOVE LATER!
            msg = f"Conflict resolved: New Monica contact with id '{monicaContact['id']}' created for '{gContactDisplayName}'"
            self.log.info(msg)
            print(msg)
            resolved = True

        # There must be exactly one candidate from user vote
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
        '''Simple search by displayname for a given Google contact. 
        Tries to find a matching Monica contact and returns its id or None if not found'''
        # Initialization
        gContactGivenName = googleContact['names'][0].get("givenName", False)
        gContactFamilyName = googleContact['names'][0].get("familyName", False)
        gContactDisplayName = googleContact['names'][0]['displayName']
        candidates = []

        # Process every Monica contact
        for monicaContact in self.monica.getContacts():
            if str(monicaContact['id']) not in self.mapping.values():
                if gContactDisplayName == monicaContact['complete_name']:
                    # If the id isnt in the database and full name matches add potential candidate to list
                    candidates.append(monicaContact)
                elif (gContactGivenName and gContactFamilyName and 
                    ' '.join([gContactGivenName, gContactFamilyName]) == monicaContact['complete_name']):
                    # Sometimes Google does some strange naming things with 'honoricPrefix' etc. try to mitigate that
                    candidates.append(monicaContact)
        
        # If there is only one candidate
        if len(candidates) == 1:
            monicaContact = candidates[0]

            # Update database and mapping
            self.database.insertData(googleContact['resourceName'],
                                    monicaContact['id'], 
                                    googleContact['names'][0]["displayName"],
                                    monicaContact['complete_name'],
                                    googleContact['metadata']['sources'][0]["updateTime"],
                                    monicaContact['updated_at'])
            self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
            return str(monicaContact['id'])

        # Simple search failed
        return None

    def __getMonicaNamesFromGoogleContact(self, googleContact: dict) -> Tuple[str,str]:
        '''Creates first and last name from a Google contact with respect to honoric
        suffix/prefix.'''
        givenName = googleContact['names'][0].get("givenName", '')
        familyName = googleContact['names'][0].get("familyName", '')
        prefix = googleContact['names'][0].get("honorificPrefix", '')
        suffix = googleContact['names'][0].get("honorificSuffix", '')
        if prefix:
            givenName = prefix + ' ' + givenName
        if suffix:
            familyName = familyName + ' ' + suffix
        return givenName, familyName
