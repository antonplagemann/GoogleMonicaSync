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
                databaseHandler: Database, syncBackToGoogle: bool, deleteMonicaContactsOnSync: bool) -> None:
        self.log = log
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler
        self.mapping = self.database.getIdMapping()
        self.nextSyncToken = self.database.getGoogleNextSyncToken()
        self.syncBack = syncBackToGoogle
        self.deleteMonicaContacts = deleteMonicaContactsOnSync

        # Debugging area :-)
        self.fakeNum = 1

    def startSync(self, syncType: str = '') -> None:
        '''Starts the next sync type depending on database data.'''
        if syncType:
            raise NotImplementedError
        if not self.mapping:
            # There is no database, so build it before syncing
            msg = "No sync database found, try building it..."
            self.log.info(msg)
            print(msg + "\n")
            self.__initialSync()
        elif not self.nextSyncToken:
            # There is a database, but no full sync has been done yet
            msg = "No sync token found, doing a full sync..."
            self.log.info(msg)
            print(msg + "\n")
            self.__sync()
        else:
            # There has been a full sync before, so do a delta sync from now on
            msg = "Sync token found, doing a delta sync..."
            self.log.info(msg)
            print(msg + "\n")
            self.__deltaSync()
        

    def __initialSync(self) -> None:
        '''Builds the syncing database and starts a full sync.'''
        self.database.deleteAndInitialize()
        self.__buildSyncDatabase()
        self.mapping = self.database.getIdMapping()
        self.__sync()

    def __deltaSync(self) -> None:
        '''Fetches every contact from Google that has changed since the last sync including deleted ones.'''
        msg = "Initializing delta sync..."
        self.log.info(msg)
        print(msg)
        googleContacts = self.google.getContacts(requestSyncToken=True, syncToken=self.nextSyncToken)
        contactCount = len(googleContacts)

        if self.deleteMonicaContacts:
            # Process every Google contact and search for deleted ones
            for num, googleContact in enumerate(googleContacts):
                sys.stdout.write(f"\rPreprocessing Google contact {num+1} of {contactCount}")
                sys.stdout.flush()
                isDeleted = googleContact.get('metadata', {}).get('deleted', False)
                if isDeleted:
                    googleId = googleContact["resourceName"]
                    try:
                        # Try to delete the corresponding contact
                        msg = f"Found deleted Google contact with id '{googleId}'. Deleting Monica contact..."
                        self.log.info(msg)
                        print("\n" + msg)
                        monicaId = self.database.findById(googleId=googleId)[1]
                        self.monica.deleteContact(monicaId)
                        self.database.delete(googleId, monicaId)
                        self.mapping.pop(googleId)
                        self.google.removeContactFromList(googleContact)
                        msg = f"Monica contact with id '{monicaId}' deleted successfully"
                        self.log.info(msg)
                        print(msg)
                    except:
                        msg = f"Failed deleting monica contact for '{googleId}'! Please delete manually!"
                        self.log.error(msg)
                        print(msg)
        
        # Deleted contacts have been processed, now do a full sync with the already fetched delta list of Google contacts
        self.__sync(syncDescription='delta')
                
        

    def __sync(self, dateBasedSync: bool = True, requestGoogleSyncToken: bool = True, syncDescription: str = 'full') -> None:
        '''Fetches every contact from Google and Monica and does a full sync.'''
        # Initialization
        msg = f"Starting {syncDescription} sync..."
        self.log.info(msg)
        print("\n" + msg)
        googleContacts = self.google.getContacts(requestSyncToken=requestGoogleSyncToken)
        contactCount = len(googleContacts)

        # If Google hasnt returned some data
        if not googleContacts:
            msg = f"No (changed) Google contacts found!"
            self.log.info(msg)
            print("\n" + msg)

        # Process every Google contact
        for num, googleContact in enumerate(googleContacts):
            sys.stdout.write(f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()

            # Skip all contacts which have not changed according to the database lastChanged date (if present)
            try:
                if dateBasedSync:
                    # Get timestamps
                    databaseTimestamp = self.database.findById(googleId=googleContact["resourceName"])[4]
                    databaseDate = self.__convertGoogleTimestamp(databaseTimestamp)
                    contactTimestamp = googleContact['metadata']['sources'][0]["updateTime"]
                    contactDate = self.__convertGoogleTimestamp(contactTimestamp)

                    # Skip if nothing has changed
                    if databaseDate == contactDate:
                        continue
            except:
                # Continue if there is no lastChanged date
                pass
            try:
                # Get Monica id from database (index 1 in returned row)
                monicaId = self.database.findById(googleId=googleContact["resourceName"])[1]
            except:
                # That must be a new Google contact
                googleId = googleContact['resourceName']
                gContactDisplayName = googleContact.get('names',[{}])[0].get('displayName', "")
                msg = f"No Monica id for '{googleId}' with name '{gContactDisplayName} found': Creating new Monica contact..."
                self.log.info(msg)
                print("\n" + msg)

                # Create new Monica contact
                monicaContact = self.__createMonicaContact(googleContact)
                msg = f"New Monica contact with id '{monicaContact['id']}' for '{gContactDisplayName}' created"
                self.log.info(msg)
                print(msg)

                # Update database and mapping
                self.database.insertData(googleContact['resourceName'],
                                monicaContact['id'], 
                                gContactDisplayName,
                                monicaContact['complete_name'])
                self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
                msg = f"New sync connection between id:'{googleContact['resourceName']}' and id:'{monicaContact['id']}' added"
                self.log.info(msg)

                # Sync additional details
                self.__syncDetails(googleContact, monicaContact)

                # Proceed with next contact
                continue

            # Get Monica contact by id
            monicaContact = self.monica.getContact(monicaId)
            
            # Merge name, birthday and deceased date and update them
            self.__mergeAndUpdateNBD(monicaContact, googleContact)

            # Sync additional details
            self.__syncDetails(googleContact, monicaContact)

        # Finished
        msg = f"{syncDescription.capitalize()} sync finished!"
        self.log.info(msg)
        print("\n" + msg)

    def __syncDetails(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs additional details, such as work, phone numbers, emails, notes, etc.'''
        pass

    def __buildSyncDatabase(self) -> None:
        '''Builds a Google <-> Monica contact id mapping and saves it to the database.'''
        # Initialization
        conflicts = []
        googleContacts = self.google.getContacts(requestSyncToken=True)
        contactCount = len(googleContacts)
        msg = "Building sync database..."
        self.log.info(msg)
        print(msg)

        # Process every Google contact
        for num, googleContact in enumerate(googleContacts):
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
                    googleContact = googleContacts[0]
                    googleContact['resourceName'] = self.__generateFakeId(self.mapping.keys())
                    gContactDisplayName = "New contact"
                    # DUMMY! REMOVE LATER!

                    # Update database and mapping
                    self.database.insertData(googleContact['resourceName'],
                                            monicaContact['id'],
                                            gContactDisplayName, 
                                            monicaContact['complete_name'])
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
                                monicaContact['complete_name'])
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
                                    monicaContact['complete_name'])
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
