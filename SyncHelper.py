# pylint: disable=import-error
import sys
from datetime import datetime
from logging import Logger
from typing import Tuple, Union, List

from DatabaseHelper import Database, DatabaseEntry
from GoogleHelper import Google, GoogleContactUploadForm
from MonicaHelper import Monica, MonicaContactUploadForm


class Sync():
    '''Handles all syncing and merging issues with Google, Monica and the database.'''

    def __init__(self, log: Logger, databaseHandler: Database, 
                 monicaHandler: Monica, googleHandler: Google, syncBackToGoogle: bool,
                 checkDatabase: bool, deleteMonicaContactsOnSync: bool, 
                 streetReversalOnAddressSync: bool, syncingFields: dict) -> None:
        self.log = log
        self.startTime = datetime.now()
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler
        self.mapping = self.database.getIdMapping()
        self.reverseMapping = {monicaId: googleId for googleId, monicaId in self.mapping.items()}
        self.nextSyncToken = self.database.getGoogleNextSyncToken()
        self.syncBack = syncBackToGoogle
        self.check = checkDatabase
        self.deleteMonicaContacts = deleteMonicaContactsOnSync
        self.streetReversal = streetReversalOnAddressSync
        self.sync = syncingFields
        self.skipCreationPrompt = False
        self.skipUnnamedPrompt = False

    def __updateMapping(self, googleId: str, monicaId: str) -> None:
        '''Updates the internal Google <-> Monica id mapping dictionary.'''
        self.mapping.update({googleId: monicaId})
        self.reverseMapping.update({monicaId: googleId})

    def startSync(self, syncType: str = '') -> None:
        '''Starts the next sync cycle depending on the requested type 
        and the database data.'''
        if syncType == 'initial':
            # Initial sync requested
            self.__initialSync()
        elif not self.mapping:
            # There is no sync database. Initial sync is needed for all other sync types
            msg = "No sync database found, please do a initial sync first!"
            self.log.info(msg)
            print(msg + "\n")
            raise Exception("Initial sync needed!")
        elif syncType == 'full':
            # As this is a full sync, get all contacts at once to save time
            self.monica.getContacts()
            # Full sync requested so dont use database timestamps here
            self.__sync('full', dateBasedSync=False)
        elif syncType == 'delta' and not self.nextSyncToken:
            # Delta sync requested but no sync token found
            msg = "No sync token found, delta sync not possible. Doing (fast) full sync instead..."
            self.log.info(msg)
            print(msg + "\n")
            # Do a full sync with database timestamp comparison (fast)
            self.__sync('full')
        elif syncType == 'delta':
            # Delta sync requested
            self.__sync('delta')
        elif syncType == 'syncBack':
            # Sync back to Google requested
            self.__syncBack()
        
        # Print statistics
        self.__printSyncStatistics()

        if self.check:
            # Database check requested
            self.checkDatabase()

    def __initialSync(self) -> None:
        '''Builds the syncing database and starts a full sync. Needs user interaction!'''
        self.database.deleteAndInitialize()
        self.mapping.clear()
        self.__buildSyncDatabase()
        print("\nThe following fields will be overwritten with Google data:")
        for field, choice in list(self.sync.items())[:-1]:
            if choice:
                print(f"- {field}")
        print("Start full sync now?")
        print("\t0: No (abort initial sync)")
        print("\t1: Yes")
        choice = int(input("Enter your choice (number only): "))
        if not choice:
            raise Exception("Sync aborted by user choice")
        self.__sync('full', dateBasedSync=False)

    def __deleteMonicaContact(self, googleContact: dict) -> None:
        '''Deletes a Monica contact given a corresponding Google contact.'''
        # Initialization
        googleId = googleContact["resourceName"]
        gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]
        msg = f"'{gContactDisplayName}' ('{googleId}'): Found deleted Google contact. Deleting Monica contact..."
        self.log.info(msg)

        try:
            # Try to delete the corresponding contact
            monicaId = self.database.findById(googleId=googleId)[1]
            self.monica.deleteContact(monicaId, gContactDisplayName)
            self.database.delete(googleId, monicaId)
            self.mapping.pop(googleId)
            self.google.removeContactFromList(googleContact)
            msg = f"'{gContactDisplayName}' ('{monicaId}'): Monica contact deleted successfully"
            self.log.info(msg)
        except:
            msg = f"'{gContactDisplayName}' ('{googleId}'): Failed deleting corresponding Monica contact! Please delete manually!"
            self.google.removeContactFromList(googleContact)
            self.log.error(msg)
            print(msg)

    def __sync(self, syncType: str, dateBasedSync: bool = True) -> None:
        '''Fetches every contact from Google and Monica and does a full sync.'''
        # Initialization
        msg = f"Starting {syncType} sync..."
        self.log.info(msg)
        print("\n" + msg)
        if syncType == 'delta':
            googleContacts = self.google.getContacts(syncToken=self.nextSyncToken)
        else:
            googleContacts = self.google.getContacts()
        contactCount = len(googleContacts)

        # If Google hasnt returned some data
        if not googleContacts:
            msg = f"No (changed) Google contacts found!"
            self.log.info(msg)
            print("\n" + msg)

        # Process every Google contact
        for num, googleContact in enumerate(googleContacts):
            sys.stdout.write(
                f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()

            # Delete Monica contact if Google contact was deleted (if chosen by user; delta sync only)
            isDeleted = googleContact.get('metadata', {}).get('deleted', False)
            if isDeleted and self.deleteMonicaContacts:
                self.__deleteMonicaContact(googleContact)
                # Skip further processing
                continue

            # Skip all contacts which have not changed according to the database lastChanged date (if present)
            try:
                # Get Monica id and timestamp
                monicaId, _, _, databaseTimestamp = self.database.findById(googleId=googleContact["resourceName"])[1:5]
                if dateBasedSync and not databaseTimestamp == 'NULL':
                    databaseDate = self.__convertGoogleTimestamp(databaseTimestamp)
                    contactTimestamp = googleContact['metadata']['sources'][0]["updateTime"]
                    contactDate = self.__convertGoogleTimestamp(contactTimestamp)

                    # Skip if nothing has changed
                    if databaseDate == contactDate:
                        continue
            except:
                # Create a new Google contact if there's nothing in the database yet
                googleId = googleContact['resourceName']
                gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]
                msg = f"'{gContactDisplayName}' ('{googleId}'): No Monica id found': Creating new Monica contact..."
                self.log.info(msg)
                print("\n" + msg)

                # Create new Monica contact
                monicaContact = self.__createMonicaContact(googleContact)
                msg = f"'{gContactDisplayName}' ('{monicaContact['id']}'): New Monica contact created"
                self.log.info(msg)
                print(msg)

                # Update database and mapping
                databaseEntry = DatabaseEntry(googleContact['resourceName'],
                                            monicaContact['id'],
                                            gContactDisplayName,
                                            monicaContact['complete_name'],
                                            googleContact['metadata']['sources'][0]['updateTime'],
                                            monicaContact['updated_at'])
                self.database.insertData(databaseEntry)
                self.__updateMapping(googleContact['resourceName'], str(monicaContact['id']))
                msg = f"'{googleContact['resourceName']}' <-> '{monicaContact['id']}': New sync connection added"
                self.log.info(msg)

                # Sync additional details
                self.__syncDetails(googleContact, monicaContact)

                # Proceed with next contact
                continue

            try:
                # Get Monica contact by id
                monicaContact = self.monica.getContact(monicaId)
            except Exception as e:
                msg = f"'{monicaId}': Failed to fetch Monica contact: {str(e)}"
                self.log.error(msg)
                print("\n" + msg)
                print("Please do not delete Monica contacts manually!")
                raise Exception("Could't connect to Monica api or Database not consistent, consider doing initial sync to rebuild.")
            # Merge name, birthday and deceased date and update them
            self.__mergeAndUpdateNBD(monicaContact, googleContact)

            # Update Google contact last changed date in the database
            self.database.update(googleId=googleContact['resourceName'],
                                 googleFullName=self.__getGoogleContactNames(googleContact)[3],
                                 googleLastChanged=googleContact['metadata']['sources'][0]['updateTime'])

            # Refresh Monica data (could have changed)
            monicaContact = self.monica.getContact(monicaId)

            # Sync additional details
            self.__syncDetails(googleContact, monicaContact)

        # Finished
        msg = f"{syncType.capitalize()} sync finished!"
        self.log.info(msg)
        print("\n" + msg)

        # Sync lonely Monica contacts back to Google if chosen by user
        if self.syncBack:
            self.__syncBack()

    def __syncDetails(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs additional details, such as company, jobtitle, labels, 
        address, phone numbers, emails, notes, contact picture, etc.'''
        if self.sync["career"]:
            # Sync career info
            self.__syncCareerInfo(googleContact, monicaContact)

        if self.sync["address"]:
            # Sync address info
            self.__syncAddress(googleContact, monicaContact)

        if self.sync["phone"] or self.sync["email"]:
            # Sync phone and email
            self.__syncPhoneEmail(googleContact, monicaContact)

        if self.sync["labels"]:
            # Sync labels
            self.__syncLabels(googleContact, monicaContact)

        if self.sync["notes"]:
            # Sync notes if not existent at Monica
            self.__syncNotes(googleContact, monicaContact)

    def __syncNotes(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs Google contact notes if there is no note present at Monica.'''
        monicaNotes = self.monica.getNotes(monicaContact["id"], monicaContact["complete_name"])
        try:
            identifier = "\n\n*This note is synced from your Google contacts. Do not edit here.*"
            if googleContact.get("biographies", []):
                # Get Google note
                googleNote = {
                "body": googleContact["biographies"][0].get("value", "").strip(),
                "contact_id": monicaContact["id"],
                "is_favorited": False
                }
                if not monicaNotes:
                    # If there is no Monica note sync the Google note
                    googleNote["body"] += identifier
                    self.monica.addNote(googleNote, monicaContact["complete_name"])
                else:
                    updated = False
                    for monicaNote in monicaNotes:
                        if monicaNote["body"] == googleNote["body"]:
                            # If there is a note with the same content update it and add the identifier
                            googleNote["body"] += identifier
                            self.monica.updateNote(monicaNote["id"], googleNote, monicaContact["complete_name"])
                            updated = True
                            break
                        elif identifier in monicaNote["body"]:
                            # Found identifier, update this note if changed
                            googleNote["body"] += identifier
                            if monicaNote["body"] != googleNote["body"]:
                                self.monica.updateNote(monicaNote["id"], googleNote, monicaContact["complete_name"])
                            updated = True
                            break
                    if not updated:
                        # No note with same content or identifier found so create a new one
                        googleNote["body"] += identifier
                        self.monica.addNote(googleNote, monicaContact["complete_name"])
            elif monicaNotes:
                for monicaNote in monicaNotes:
                    if identifier in monicaNote["body"]:
                        # Found identifier, delete this note
                        self.monica.deleteNote(monicaNote["id"], monicaNote["contact"]["id"], monicaContact["complete_name"])
                        break

        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error creating Monica note: {str(e)}"
            self.log.warning(msg)

    def __syncLabels(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs Google contact labels/groups/tags.'''
        try:
            # Get google labels information
            googleLabels = [
                self.google.getLabelName(
                    label["contactGroupMembership"]["contactGroupResourceName"])
                for label in googleContact.get("memberships", [])
            ]

            # Remove tags if not present in Google contact
            removeList = [label["id"] for label in monicaContact["tags"]
                          if label["name"] not in googleLabels]
            if removeList:
                self.monica.removeTags({"tags": removeList}, monicaContact["id"], monicaContact["complete_name"])

            # Update labels if neccessary
            monicaLabels = [label["name"]
                            for label in monicaContact["tags"] if label["name"] in googleLabels]
            if sorted(googleLabels) != sorted(monicaLabels):
                self.monica.addTags({"tags": googleLabels}, monicaContact["id"], monicaContact["complete_name"])

        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica contact labels: {str(e)}"
            self.log.warning(msg)

    def __syncPhoneEmail(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs phone and email fields.'''
        monicaContactFields = self.monica.getContactFields(monicaContact['id'], monicaContact['complete_name'])
        if self.sync["email"]:
            self.__syncEmail(googleContact, monicaContact, monicaContactFields)
        if self.sync["phone"]:
            self.__syncPhone(googleContact, monicaContact, monicaContactFields)

    def __syncEmail(self, googleContact: dict, monicaContact: dict, monicaContactFields: dict) -> None:
        '''Syncs email fields.'''
        try:
            # Email processing
            monicaContactEmails = [
                field for field in monicaContactFields 
                if field["contact_field_type"]["type"] == "email"]
            googleContactEmails = googleContact.get("emailAddresses", [])

            if googleContactEmails:
                googleEmails = [
                    {
                    "contact_field_type_id": 1,
                    "data": email["value"].strip(),
                    "contact_id": monicaContact["id"]
                    } 
                    for email in googleContactEmails
                ]
                if monicaContactEmails:
                    # There is Google and Monica data: Check and recreate emails
                    for monicaEmail in monicaContactEmails:
                        # Check if there are emails to be deleted
                        if monicaEmail["content"] in [googleEmail["data"] for googleEmail in googleEmails]:
                            continue
                        else:
                            self.monica.deleteContactField(monicaEmail["id"], monicaContact["id"], monicaContact["complete_name"])
                    for googleEmail in googleEmails:
                        # Check if there are emails to be created
                        if googleEmail["data"] in [monicaEmail["content"] for monicaEmail in monicaContactEmails]:
                            continue
                        else:
                            self.monica.createContactField(monicaContact["id"], googleEmail, monicaContact["complete_name"])
                else:
                    # There is only Google data: Create emails
                    for googleEmail in googleEmails:
                        self.monica.createContactField(monicaContact["id"], googleEmail, monicaContact["complete_name"])

            elif monicaContactEmails:
                # Delete Monica contact emails
                for monicaEmail in monicaContactEmails:
                    self.monica.deleteContactField(monicaEmail["id"], monicaContact["id"], monicaContact["complete_name"])
        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica contact email: {str(e)}"
            self.log.warning(msg)

    def __syncPhone(self, googleContact: dict, monicaContact: dict, monicaContactFields: dict) -> None:
        '''Syncs phone fields.'''
        try:
            # Phone number processing
            monicaContactPhones = [
                field for field in monicaContactFields 
                if field["contact_field_type"]["type"] == "phone"]
            googleContactPhones = googleContact.get("phoneNumbers", [])

            if googleContactPhones:
                googlePhones = [
                    {
                    "contact_field_type_id": 2,
                    "data": number["value"].strip(),
                    "contact_id": monicaContact["id"]
                    } 
                    for number in googleContactPhones
                ]
                if monicaContactPhones:
                    # There is Google and Monica data: Check and recreate phone numbers
                    for monicaPhone in monicaContactPhones:
                        # Check if there are phone numbers to be deleted
                        if monicaPhone["content"] in [googlePhone["data"] for googlePhone in googlePhones]:
                            continue
                        else:
                            self.monica.deleteContactField(monicaPhone["id"], monicaContact["id"], monicaContact["complete_name"])
                    for googlePhone in googlePhones:
                        # Check if there are phone numbers to be created
                        if googlePhone["data"] in [monicaPhone["content"] for monicaPhone in monicaContactPhones]:
                            continue
                        else:
                            self.monica.createContactField(monicaContact["id"], googlePhone, monicaContact["complete_name"])
                else:
                    # There is only Google data: Create phone numbers
                    for googlePhone in googlePhones:
                        self.monica.createContactField(monicaContact["id"], googlePhone, monicaContact["complete_name"])

            elif monicaContactPhones:
                # Delete Monica contact phone numbers
                for monicaPhone in monicaContactPhones:
                    self.monica.deleteContactField(monicaPhone["id"], monicaContact["id"], monicaContact["complete_name"])

        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica contact phone: {str(e)}"
            self.log.warning(msg)

    def __syncCareerInfo(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs company and job title fields.'''
        try:
            monicaDataPresent = bool(monicaContact["information"]["career"]["job"] or
                                 monicaContact["information"]["career"]["company"])
            googleDataPresent = bool(googleContact.get("organizations", False))
            if googleDataPresent or monicaDataPresent:
                # Get google career information
                company = googleContact.get("organizations", [{}])[0].get("name", "").strip()
                department = googleContact.get("organizations", [{}])[0].get("department", "").strip()
                if department:
                    department = f"; {department}"
                job = googleContact.get("organizations", [{}])[0].get("title", None)
                googleData = {
                    "job": job.strip() if job else None,
                    "company": company + department if company or department else None
                }
                # Get monica career information
                monicaData = {
                    "job": monicaContact['information']['career'].get('job', None),
                    "company": monicaContact['information']['career'].get('company', None)
                }

                # Compare and update if neccessary
                if googleData != monicaData:
                    self.monica.updateCareer(monicaContact["id"], googleData)
        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica contact career: {str(e)}"
            self.log.warning(msg)

    def __syncAddress(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs all address fields.'''
        try:
            monicaDataPresent = bool(monicaContact.get("addresses", False))
            googleDataPresent = bool(googleContact.get("addresses", False))
            if googleDataPresent:
                # Get Google data
                googleAddressList = []
                for addr in googleContact.get("addresses", []):
                    # None type is important for comparison, empty string won't work here
                    name = None
                    street = None
                    city = None
                    province = None
                    postalCode = None
                    countryCode = None
                    street = addr.get("streetAddress", "").replace("\n", " ").strip() or None
                    if self.streetReversal:
                        # Street reversal: from '13 Auenweg' to 'Auenweg 13'
                        try: 
                            if street and street[0].isdigit():
                                street = f'{street[street.index(" ")+1:]} {street[:street.index(" ")]}'.strip()
                        except:
                            pass
                    
                    # Get (extended) city
                    city = f'{addr.get("city", "")} {addr.get("extendedAddress", "")}'.strip() or None
                    # Get other details
                    province = addr.get("region", None)
                    postalCode = addr.get("postalCode", None)
                    countryCode = addr.get("countryCode", None)
                    # Name can not be empty
                    name = addr.get("formattedType", None) or "Other"
                    # Do not sync empty addresses
                    if not any([street, city, province, postalCode, countryCode]):
                        continue
                    googleAddressList.append({
                        'name': name,
                        'street': street,
                        'city': city,
                        'province': province,
                        'postal_code': postalCode,
                        'country': countryCode,
                        'contact_id': monicaContact['id']
                    })
            
            if monicaDataPresent:
                # Get Monica data
                monicaAddressList = []
                for addr in monicaContact.get("addresses", []):
                    monicaAddressList.append({addr["id"]: {
                        'name': addr["name"],
                        'street': addr["street"],
                        'city': addr["city"],
                        'province': addr["province"],
                        'postal_code': addr["postal_code"],
                        'country': addr["country"].get("iso", None) if addr["country"] else None,
                        'contact_id': monicaContact['id']
                    }})

            if googleDataPresent and monicaDataPresent:
                monicaPlainAddressList = [monicaAddress for item in monicaAddressList for monicaAddress in item.values()]
                # Do a complete comparison
                if all([googleAddress in monicaPlainAddressList for googleAddress in googleAddressList]):
                    # All addresses are equal, nothing to do
                    return
                else:
                    # Delete all Monica addresses and create new ones afterwards
                    # Safest way, I don't want to code more deeper comparisons and update functions
                    for element in monicaAddressList:
                        for addressId, _ in element.items():
                            self.monica.deleteAddress(addressId, monicaContact["id"], monicaContact["complete_name"])
            elif not googleDataPresent and monicaDataPresent:
                # Delete all Monica addresses
                for element in monicaAddressList:
                    for addressId, _ in element.items():
                        self.monica.deleteAddress(addressId, monicaContact["id"], monicaContact["complete_name"])

            if googleDataPresent:
                # All old Monica data (if existed) have been cleaned now, proceed with address creation
                for googleAddress in googleAddressList:
                    self.monica.createAddress(googleAddress, monicaContact["complete_name"])
                            
        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica addresses: {str(e)}"
            self.log.warning(msg)

    def __buildSyncDatabase(self) -> None:
        '''Builds a Google <-> Monica 1:1 contact id mapping and saves it to the database.'''
        # Initialization
        conflicts = []
        googleContacts = self.google.getContacts()
        self.monica.getContacts()
        contactCount = len(googleContacts)
        msg = "Building sync database..."
        self.log.info(msg)
        print("\n" + msg)

        # Process every Google contact
        for num, googleContact in enumerate(googleContacts):
            sys.stdout.write(f"\rProcessing Google contact {num+1} of {contactCount}")
            sys.stdout.flush()
            # Try non-interactive search first
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

        # Finished
        msg = "Sync database built!"
        self.log.info(msg)
        print("\n" + msg)

    def __syncBack(self) -> None:
        '''Sync lonely Monica contacts back to Google by creating a new contact there.'''
        msg = "Starting sync back..."
        self.log.info(msg)
        print("\n" + msg)
        monicaContacts = self.monica.getContacts()
        contactCount = len(monicaContacts)

        # Process every Monica contact
        for num, monicaContact in enumerate(monicaContacts):
            sys.stdout.write(f"\rProcessing Monica contact {num+1} of {contactCount}")
            sys.stdout.flush()

            # If there the id isnt in the database: create a new Google contact and upload
            if str(monicaContact['id']) not in self.mapping.values():
                # Create Google contact
                googleContact = self.__createGoogleContact(monicaContact)
                if not googleContact:
                    msg = f"'{monicaContact['complete_name']}': Error encountered at creating new Google contact. Skipping..."
                    self.log.warning(msg)
                    print(msg)
                    continue
                gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]

                # Update database and mapping
                databaseEntry = DatabaseEntry(googleContact['resourceName'],
                                            monicaContact['id'],
                                            gContactDisplayName,
                                            monicaContact['complete_name'])
                self.database.insertData(databaseEntry)
                msg = f"'{gContactDisplayName}' ('{googleContact['resourceName']}'): New google contact created (sync back)"
                print("\n" + msg)
                self.log.info(msg)
                self.__updateMapping(googleContact['resourceName'], str(monicaContact['id']))
                msg = f"'{googleContact['resourceName']}' <-> '{monicaContact['id']}': New sync connection added"
                self.log.info(msg)

        if not self.google.createdContacts:
            msg = "No contacts for sync back found"
            self.log.info(msg)
            print("\n" + msg)

        # Finished
        msg = "Sync back finished!"
        self.log.info(msg)
        print(msg)

    def __printSyncStatistics(self) -> None:
        '''Prints and logs a pretty sync statistic of the last sync.'''
        self.monica.updateStatistics()
        tme = str(datetime.now() - self.startTime).split(".")[0] + "h"
        gAp = str(self.google.apiRequests) + (8-len(str(self.google.apiRequests))) * ' '
        mAp = str(self.monica.apiRequests) + (8-len(str(self.monica.apiRequests))) * ' '
        mCC = str(len(self.monica.createdContacts)) + (8-len(str(len(self.monica.createdContacts)))) * ' '
        mCU = str(len(self.monica.updatedContacts)) + (8-len(str(len(self.monica.updatedContacts)))) * ' '
        mCD = str(len(self.monica.deletedContacts)) + (8-len(str(len(self.monica.deletedContacts)))) * ' '
        gCC = str(len(self.google.createdContacts)) + (8-len(str(len(self.google.createdContacts)))) * ' '
        msg = "\n" \
        f"Sync statistics: \n" \
        f"+-------------------------------------+\n" \
        f"| Syncing time:             {tme   }  |\n" \
        f"| Google api calls used:    {gAp   }  |\n" \
        f"| Monica api calls used:    {mAp   }  |\n" \
        f"| Monica contacts created:  {mCC   }  |\n" \
        f"| Monica contacts updated:  {mCU   }  |\n" \
        f"| Monica contacts deleted:  {mCD   }  |\n" \
        f"| Google contacts created:  {gCC   }  |\n" \
        f"+-------------------------------------+"
        print(msg)
        self.log.info(msg)

    def __createGoogleContact(self, monicaContact: dict) -> dict:
        '''Creates a new Google contact from a given Monica contact and returns it.'''
        # Get names (no nickname)
        firstName = monicaContact['first_name'] or ''
        lastName = monicaContact['last_name'] or ''
        fullName = monicaContact['complete_name'] or ''
        nickname = monicaContact['nickname'] or ''
        middleName = self.__getMonicaMiddleName(firstName, lastName, nickname, fullName)

        # Get birthday details (age based birthdays are not supported by Google)
        birthday = {}
        birthdayTimestamp = monicaContact['information']["dates"]["birthdate"]["date"]
        ageBased = monicaContact['information']["dates"]["birthdate"]["is_age_based"]
        if birthdayTimestamp and not ageBased:
            yearUnknown = monicaContact['information']["dates"]["birthdate"]["is_year_unknown"]
            date = self.__convertMonicaTimestamp(birthdayTimestamp)
            if not yearUnknown:
                birthday.update({
                    'year': date.year
                })
            birthday.update({
                'month': date.month,
                'day': date.day
            })

        # Get addresses
        addresses = monicaContact["addresses"] if self.sync["address"] else []

        # Get career info if exists
        career = {key: value for key, value in monicaContact['information']["career"].items()
                if value and self.sync["career"]}

        # Get phone numbers and email addresses
        if self.sync["phone"] or self.sync["email"]:   
            monicaContactFields = self.monica.getContactFields(monicaContact['id'], monicaContact['complete_name'])
            # Get email addresses
            emails = [field["content"] for field in monicaContactFields 
                    if field["contact_field_type"]["type"] == "email"
                    and self.sync["email"]]
            # Get phone numbers
            phoneNumbers = [field["content"] for field in monicaContactFields 
                            if field["contact_field_type"]["type"] == "phone"
                            and self.sync["phone"]]

        # Get tags/labels and create them if neccessary
        labelIds = [self.google.getLabelId(tag['name'])
            for tag in monicaContact["tags"]
            if self.sync["labels"]]

        # Create contact upload form
        form = GoogleContactUploadForm(firstName=firstName, lastName=lastName,
                                       middleName=middleName, birthdate=birthday,
                                       phoneNumbers=phoneNumbers, career=career,
                                       emailAdresses=emails, labelIds=labelIds,
                                       addresses=addresses)

        # Upload contact
        contact = self.google.createContact(data=form.getData())

        return contact

    def __getMonicaMiddleName(self, firstName: str, lastName: str, nickname: str, fullName: str) -> str:
        '''Monica contacts have for some reason a hidden field middlename that can be set (creation/update)
        but sadly can not retrieved later. This function computes it by using the complete_name field.'''
        try:
            # If there is a nickname it will be parenthesized with a space
            nicknameLength = len(nickname) + 3 if nickname else 0
            middleName = fullName[len(firstName):len(fullName) - (len(lastName) + nicknameLength)].strip()
            return middleName
        except:
            return ''

    def checkDatabase(self) -> None:
        '''Checks if there are orphaned database entries which need to be resolved.
        The following checks and assumptions will be made:
        1. Google contact id NOT IN database
           -> Info: contact is currently not in sync
        2. Google contact id IN database BUT Monica contact not found
           -> Error: deleted Monica contact or wrong id
        3. Monica contact id NOT IN database
           -> Info: contact is currently not in sync
        4. Monica contact id IN database BUT Google contact not found
           -> Error: deleted Google contact or wrong id
        5. Google contact id IN database BUT Monica AND Google contact not found
           -> Warning: orphaned database entry'''
        # Initialization
        startTime = datetime.now()
        googleContactsNotSynced = []
        googleContactsSynced = []
        monicaContactsNotSynced = []
        monicaContactsSynced = []
        errors = 0
        msg = f"Starting database check..."
        self.log.info(msg)
        print("\n" + msg)

        # Get contacts
        googleContacts = self.google.getContacts(refetchData=True, requestSyncToken=False)
        googleContactsCount = len(googleContacts)
        monicaContacts = self.monica.getContacts()
        monicaContactsCount = len(monicaContacts)

        # Check every Google contact
        for num, googleContact in enumerate(googleContacts):
            sys.stdout.write(
                f"\rProcessing Google contact {num+1} of {googleContactsCount}")
            sys.stdout.flush()

            # Get monica id
            monicaId = self.mapping.get(googleContact['resourceName'], None)
            if not monicaId:
                googleContactsNotSynced.append(googleContact)
                continue

            # Get monica contact
            try:
                monicaContact = self.monica.getContact(monicaId)
                assert monicaContact
                monicaContactsSynced.append(monicaContact)
            except:
                errors += 1
                msg = f"'{self.__getGoogleContactNames(googleContact)[3]}' ('{googleContact['resourceName']}'): " \
                      f"Wrong id or missing Monica contact for id '{monicaId}'."
                self.log.error(msg)
                print("\nError: " + msg)

        # Print a newline to avoid overwriting console output
        print("")

        # Check every Monica contact
        for num, monicaContact in enumerate(monicaContacts):
            sys.stdout.write(
                f"\rProcessing Monica contact {num+1} of {monicaContactsCount}")
            sys.stdout.flush()

            # Get monica id
            googleId = self.reverseMapping.get(str(monicaContact["id"]), None)
            if not googleId:
                monicaContactsNotSynced.append(monicaContact)
                continue

            # Get Monica contact
            try:
                googleContact = self.google.getContact(googleId)
                assert googleContact
                googleContactsSynced.append(googleContact)
            except:
                errors += 1
                msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): " \
                      f"Wrong id or missing Google contact for id '{googleId}'."
                self.log.error(msg)
                print("\nError: " + msg)

        # Check for orphaned database entrys
        googleIds = [c['resourceName'] for c in googleContacts]
        monicaIds = [str(c['id']) for c in monicaContacts]
        orphanedEntrys = [googleId for googleId, monicaId in self.mapping.items()
                          if googleId not in googleIds
                          and monicaId not in monicaIds]

        # Log results
        if orphanedEntrys:
            self.log.info("The following database entrys are orphaned:")
            for googleId in orphanedEntrys:
                monicaId, googleFullName, monicaFullName = self.database.findById(googleId)[1:4]
                self.log.warning(f"'{googleId}' <-> '{monicaId}' ('{googleFullName}' <-> '{monicaFullName}')")
                self.log.info("This doesn't cause sync errors, but you can fix it doing initial sync '-i'")
        if not monicaContactsNotSynced and not googleContactsNotSynced:
            self.log.info("All contacts are currently in sync")
        elif monicaContactsNotSynced:
            self.log.info("The following Monica contacts are currently not in sync:")
            for monicaContact in monicaContactsNotSynced:
                self.log.info(f"'{monicaContact['complete_name']}' ('{monicaContact['id']}')")
            self.log.info("You can do a sync back '-sb' to fix that")
        if googleContactsNotSynced:
            self.log.info("The following Google contacts are currently not in sync:")
            for googleContact in googleContactsNotSynced:
                googleId = googleContact['resourceName']
                gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]
                self.log.info(f"'{gContactDisplayName}' ('{googleId}')")
            self.log.info("You can do a full sync '-f' to fix that")

        # Finished
        if errors:
            msg = f"Database check failed. Consider doing initial sync '-i' again!"
        else:
            msg = f"Database check finished, no errors found!"
        self.log.info(msg)
        print("\n" + msg)

        # Print and log statistics
        self.__printCheckStatistics(startTime, errors, len(orphanedEntrys),
                                    len(monicaContactsNotSynced), len(googleContactsNotSynced),
                                    monicaContactsCount, googleContactsCount)

    def __printCheckStatistics(self, startTime: str, errors: int, orphaned: int,
                               monicaContactsNotSyncedCount: int, googleContactsNotSyncedCount: int,
                               monicaContactsCount: int, googleContactsCount: int) -> None:
        '''Prints and logs a pretty check statistic of the last database check.'''
        tme = str(datetime.now() - startTime).split(".")[0] + "h"
        err = str(errors) + (8-len(str(errors))) * ' '
        oph = str(orphaned) + (8-len(str(orphaned))) * ' '
        mNS = str(monicaContactsNotSyncedCount) + (8-len(str(monicaContactsNotSyncedCount))) * ' '
        gNS = str(googleContactsNotSyncedCount) + (8-len(str(googleContactsNotSyncedCount))) * ' '
        cMC = str(monicaContactsCount) + (8-len(str(monicaContactsCount))) * ' '
        cGC = str(googleContactsCount) + (8-len(str(googleContactsCount))) * ' '
        msg = "\n" \
        f"Check statistics: \n" \
        f"+-----------------------------------------+\n" \
        f"| Check time:                   {tme   }  |\n" \
        f"| Errors:                       {err   }  |\n" \
        f"| Orphaned database entrys:     {oph   }  |\n" \
        f"| Monica contacts not in sync:  {mNS   }  |\n" \
        f"| Google contacts not in sync:  {gNS   }  |\n" \
        f"| Checked Monica contacts:      {cMC   }  |\n" \
        f"| Checked Google contacts:      {cGC   }  |\n" \
        f"+-----------------------------------------+"
        print(msg)
        self.log.info(msg)

    def __mergeAndUpdateNBD(self, monicaContact: dict, googleContact: dict) -> dict:
        '''Updates names, birthday and deceased date by merging an existing Monica contact with
        a given Google contact.'''
        # Get names
        firstName, lastName = self.__getMonicaNamesFromGoogleContact(googleContact)
        middleName = self.__getGoogleContactNames(googleContact)[1]
        displayName = self.__getGoogleContactNames(googleContact)[3]
        # First name is required for Monica
        if not firstName:
            firstName = displayName
            lastName = ''
        if not any([firstName, lastName, middleName, displayName]):
            self.log.info(f"Empty name for '{googleContact['resourceName']}' detected -> using Monica name instead.")
            firstName = monicaContact['first_name']

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
        googleForm = MonicaContactUploadForm(firstName=firstName, lastName=lastName, nickName=monicaContact["nickname"],
                                       middleName=middleName, genderType=monicaContact["gender_type"],
                                       birthdateDay=birthdateDay, birthdateMonth=birthdateMonth,
                                       birthdateYear=birthdateYear, isBirthdateKnown=bool(birthday),
                                       isDeceased=monicaContact["is_dead"], isDeceasedDateKnown=bool(deceasedDate),
                                       deceasedYear=deceasedYear, deceasedMonth=deceasedMonth,
                                       deceasedDay=deceasedDay, deceasedAgeBased=deceasedDateIsAgeBased,
                                       createReminders=self.monica.createReminders)

        # Check if contacts are already equal
        monicaForm = self.__getMonicaForm(monicaContact)
        #if all([googleForm.data[key] == monicaForm.data[key] for key in googleForm.data.keys() if key != 'birthdate_year']):
        if googleForm.data == monicaForm.data:
            return

        # Upload contact
        self.monica.updateContact(monicaId=monicaContact["id"], data=googleForm.data)

    def __getMonicaForm(self, monicaContact: dict) -> MonicaContactUploadForm:
        '''Creates a Monica contact upload form from a given Monica contact for comparison.'''
        # Get names
        firstName = monicaContact['first_name'] or ''
        lastName = monicaContact['last_name'] or ''
        fullName = monicaContact['complete_name'] or ''
        nickname = monicaContact['nickname'] or ''
        middleName = self.__getMonicaMiddleName(firstName, lastName, nickname, fullName)

        # Get birthday details
        birthdayTimestamp = monicaContact['information']["dates"]["birthdate"]["date"]
        birthdateYear, birthdateMonth, birthdateDay = None, None, None
        if birthdayTimestamp:
            yearUnknown = monicaContact['information']["dates"]["birthdate"]["is_year_unknown"]   
            date = self.__convertMonicaTimestamp(birthdayTimestamp)
            birthdateYear = date.year if not yearUnknown else None
            birthdateMonth = date.month
            birthdateDay = date.day

        
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
        return MonicaContactUploadForm(firstName=firstName, lastName=lastName, nickName=monicaContact["nickname"],
                                       middleName=middleName, genderType=monicaContact["gender_type"],
                                       birthdateDay=birthdateDay, birthdateMonth=birthdateMonth,
                                       birthdateYear=birthdateYear, isBirthdateKnown=bool(birthdayTimestamp),
                                       isDeceased=monicaContact["is_dead"], isDeceasedDateKnown=bool(deceasedDate),
                                       deceasedYear=deceasedYear, deceasedMonth=deceasedMonth,
                                       deceasedDay=deceasedDay, deceasedAgeBased=deceasedDateIsAgeBased,
                                       createReminders=self.monica.createReminders)

    def __createMonicaContact(self, googleContact: dict) -> dict:
        '''Creates a new Monica contact from a given Google contact and returns it.'''
        # Get names
        firstName, lastName = self.__getMonicaNamesFromGoogleContact(googleContact)
        middleName = self.__getGoogleContactNames(googleContact)[1]
        displayName = self.__getGoogleContactNames(googleContact)[3]
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
        form = MonicaContactUploadForm(firstName=firstName, lastName=lastName, middleName=middleName,
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
        candidates = []
        gContactGivenName = self.__getGoogleContactNames(googleContact)[0]
        gContactFamilyName = self.__getGoogleContactNames(googleContact)[2]
        gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]
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
        choice = None
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
            # Ask user if not done before
            if not choice and not self.skipCreationPrompt:
                print(f"\nNo Monica contact has been found for '{gContactDisplayName}'")
                print(f"\tCreate a new Monica contact?")
                print("\t0: No (abort initial sync)")
                print("\t1: Yes")
                print("\t2: Yes to all")
                choice = int(input("Enter your choice (number only): "))
                if not choice:
                    raise Exception("Sync aborted by user choice")
                if choice == 2:
                    # Skip further contact creation prompts 
                    self.skipCreationPrompt = True

            # Create new Monica contact
            monicaContact = self.__createMonicaContact(googleContact)
            msg = f"Conflict resolved: '{gContactDisplayName}' ('{monicaContact['id']}'): New Monica contact created"

        # There must be exactly one candidate from user vote
        else:
            monicaContact = candidates[0]

        # Update database and mapping
        databaseEntry = DatabaseEntry(googleContact['resourceName'],
                                    monicaContact['id'],
                                    gContactDisplayName,
                                    monicaContact['complete_name'])
        self.database.insertData(databaseEntry)
        self.__updateMapping(googleContact['resourceName'], str(monicaContact['id']))

        # Print success
        msg = f"'{googleContact['resourceName']}' <-> '{monicaContact['id']}': New sync connection added"
        self.log.info(msg)
        print("Conflict resolved: " + msg)

        return str(monicaContact['id'])

    # pylint: disable=unsubscriptable-object
    def __simpleMonicaIdSearch(self, googleContact: dict) -> Union[str, None]:
        '''Simple search by displayname for a given Google contact. 
        Tries to find a matching Monica contact and returns its id or None if not found'''
        # Initialization
        gContactGivenName = self.__getGoogleContactNames(googleContact)[0]
        gContactFamilyName = self.__getGoogleContactNames(googleContact)[2]
        gContactDisplayName = self.__getGoogleContactNames(googleContact)[3]
        candidates = []

        # Handle empty names
        if not any([gContactGivenName, gContactFamilyName, gContactDisplayName]):
            self.log.info(f"Empty name for '{googleContact['resourceName']}' detected, starting resolving procedure...")
            gContactGivenName = self.__handleEmptyGoogleNames(googleContact)

        # Process every Monica contact
        for monicaContact in self.monica.getContacts():
            if str(monicaContact['id']) not in self.mapping.values():
                if gContactDisplayName == monicaContact['complete_name']:
                    # If the id isnt in the database and full name matches add potential candidate to list
                    candidates.append(monicaContact)
                elif (gContactGivenName and gContactFamilyName and
                      ' '.join([gContactGivenName, gContactFamilyName]) == monicaContact['complete_name']):
                    # Sometimes Google does some strange naming things with 'honoricPrefix' etc.; try to mitigate that
                    candidates.append(monicaContact)

        # If there is only one candidate
        if len(candidates) == 1:
            monicaContact = candidates[0]

            # Update database and mapping
            databaseEntry = DatabaseEntry(googleContact['resourceName'],
                                        monicaContact['id'],
                                        gContactDisplayName,
                                        monicaContact['complete_name'])
            self.database.insertData(databaseEntry)
            self.__updateMapping(googleContact['resourceName'], str(monicaContact['id']))
            return str(monicaContact['id'])

        # Simple search failed
        return None

    def __getMonicaNamesFromGoogleContact(self, googleContact: dict) -> Tuple[str, str]:
        '''Creates first and last name from a Google contact with respect to honoric
        suffix/prefix.'''
        givenName, _, familyName, _, prefix, suffix = self.__getGoogleContactNames(googleContact)
        if prefix:
            givenName = f"{prefix} {givenName}".strip()
        if suffix:
            familyName = f"{familyName} {suffix}".strip()
        return givenName, familyName

    def __getGoogleContactNames(self, googleContact: dict) -> Tuple[str, str, str, str, str, str]:
        '''Returns the given, family and display name of a Google contact.'''
        names = googleContact.get('names', [{}])[0]
        givenName = names.get("givenName", '')
        familyName = names.get("familyName", '')
        displayName = names.get("displayName", '')
        middleName = names.get("middleName", '')
        prefix = names.get("honorificPrefix", '')
        suffix = names.get("honorificSuffix", '')
        return givenName, middleName, familyName, displayName, prefix, suffix

    def __handleEmptyGoogleNames(self, googleContact: dict) -> str:
        '''Ask the user for a new given name.'''

        return ''