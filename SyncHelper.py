# pylint: disable=import-error
from DatabaseHelper import Database
from MonicaHelper import Monica, MonicaContactUploadForm
from GoogleHelper import Google, GoogleContactUploadForm
from logging import Logger
from datetime import datetime
from typing import Tuple, Union
import sys


class Sync():
    '''Handles all syncing and merging issues with Google, Monica and the database.'''

    def __init__(self, log: Logger, monicaHandler: Monica, googleHandler: Google,
                 databaseHandler: Database, syncBackToGoogle: bool, 
                 deleteMonicaContactsOnSync: bool, streetReversalOnAddressSync: bool) -> None:
        self.log = log
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler
        self.mapping = self.database.getIdMapping()
        self.nextSyncToken = self.database.getGoogleNextSyncToken()
        self.syncBack = syncBackToGoogle
        self.deleteMonicaContacts = deleteMonicaContactsOnSync
        self.streetReversal = streetReversalOnAddressSync

        # Debugging area :-)
        self.fakeNum = 1

    def startSync(self, syncType: str = '') -> None:
        '''Starts the next sync type depending on database data.'''
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
            self.__sync(dateBasedSync=False)
        elif syncType == 'delta' and not self.nextSyncToken:
            # Delta sync requested but no sync token found
            msg = "No sync token found, delta sync not possible. Doing (fast) full sync instead..."
            self.log.info(msg)
            print(msg + "\n")
            self.__sync()
        elif syncType == 'delta':
            # Delta sync requested
            self.__deltaSync()
        elif syncType == 'syncBack':
            # Sync back to Google requested
            self.__syncBack()

    def __initialSync(self) -> None:
        '''Builds the syncing database and starts a full sync. Needs user interaction!'''
        self.database.deleteAndInitialize()
        self.mapping.clear()
        self.__buildSyncDatabase()
        self.mapping = self.database.getIdMapping()
        self.__sync(syncDescription='full')

    def __deltaSync(self) -> None:
        '''Fetches every contact from Google that has changed since the last sync including deleted ones.'''
        msg = "Initializing delta sync..."
        self.log.info(msg)
        print("\n" + msg)
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
                        gContactDisplayName = googleContact.get('names', [{}])[0].get('displayName', "")
                        msg = f"'{gContactDisplayName}' ('{googleId}'): Found deleted Google contact. Deleting Monica contact..."
                        self.log.info(msg)
                        print("\n" + msg)
                        monicaId = self.database.findById(googleId=googleId)[1]
                        self.monica.deleteContact(monicaId, gContactDisplayName)
                        self.database.delete(googleId, monicaId)
                        self.mapping.pop(googleId)
                        self.google.removeContactFromList(googleContact)
                        msg = f"'{gContactDisplayName}' ('{monicaId}'): Monica contact deleted successfully"
                        self.log.info(msg)
                        print(msg)
                    except:
                        msg = f"'{gContactDisplayName}' ('{googleId}'): Failed deleting corresponding Monica contact! Please delete manually!"
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
            sys.stdout.write(
                f"\rProcessing Google contact {num+1} of {contactCount}")
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

            # Update Google contact last changed date in the database
            self.database.update(googleId=googleContact['resourceName'],
                                 googleFullName=googleContact['names'][0]['displayName'],
                                 googleLastChanged=googleContact['metadata']['sources'][0]['updateTime'])
            try:
                # Get Monica id from database (index 1 in returned row)
                monicaId = self.database.findById(googleId=googleContact["resourceName"])[1]
            except:
                # That must be a new Google contact
                googleId = googleContact['resourceName']
                gContactDisplayName = googleContact.get('names', [{}])[0].get('displayName', "")
                msg = f"'{gContactDisplayName}' ('{googleId}'): No Monica id found': Creating new Monica contact..."
                self.log.info(msg)
                print("\n" + msg)

                # Create new Monica contact
                monicaContact = self.__createMonicaContact(googleContact)
                msg = f"'{gContactDisplayName}' ('{monicaContact['id']}'): New Monica contact created"
                self.log.info(msg)
                print(msg)

                # Update database and mapping
                self.database.insertData(googleContact['resourceName'],
                                         monicaContact['id'],
                                         gContactDisplayName,
                                         monicaContact['complete_name'],
                                         googleContact['metadata']['sources'][0]['updateTime'],
                                         monicaContact['updated_at'])
                self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
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

            # Refresh data
            monicaContact = self.monica.getContact(monicaId)

            # Sync additional details
            self.__syncDetails(googleContact, monicaContact)

        # Finished
        msg = f"{syncDescription.capitalize()} sync finished!"
        self.log.info(msg)
        print("\n" + msg)

        # Sync lonely Monica contacts back to Google if chosen by user
        if self.syncBack:
            self.__syncBack()

    def __syncDetails(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs additional details, such as company, jobtitle, labels, 
        address, phone numbers, emails, notes, contact picture, etc.'''
        # If you do not want to sync certain fields you can safely
        # comment out the following functions
        
        # Sync career info
        self.__syncCareerInfo(googleContact, monicaContact)

        # Sync address info
        self.__syncAddress(googleContact, monicaContact)

        # Sync phone and email
        self.__syncPhoneEmail(googleContact, monicaContact)

        # Sync labels
        self.__syncLabels(googleContact, monicaContact)

        # Work in progress

    def __syncLabels(self, googleContact: dict, monicaContact: dict) -> None:
        '''Syncs Google contact labels/groups/tags.'''
        try:
            # Get google labels information
            googleLabels = [
                self.google.reversedLabelMapping[
                    label["contactGroupMembership"]["contactGroupResourceName"]]
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
        monicaContactEmails = [
            field for field in monicaContactFields if field["contact_field_type"]["type"] == "email"]
        monicaContactPhones = [
            field for field in monicaContactFields if field["contact_field_type"]["type"] == "phone"]
        googleContactPhones = googleContact.get("phoneNumbers", [])
        googleContactEmails = googleContact.get("emailAddresses", [])
        try:
            # Email processing
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

            # Phone number processing
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

            elif monicaContactEmails:
                # Delete Monica contact phone numbers
                for monicaPhone in monicaContactPhones:
                    self.monica.deleteContactField(monicaPhone["id"], monicaContact["id"], monicaContact["complete_name"])

        except Exception as e:
            msg = f"'{monicaContact['complete_name']}' ('{monicaContact['id']}'): Error updating Monica contact email or phone: {str(e)}"
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
                    street = addr.get("streetAddress", "").replace("\n", " ").strip()
                    # Convert "" (empty string) to None
                    street = street if street else None
                    if self.streetReversal:
                        # Street reversal: from '13 Auenweg' to 'Auenweg 13'
                        try: 
                            if street and street[0].isdigit():
                                street = f'{street[street.index(" ")+1:]} {street[:street.index(" ")]}'.strip()
                        except:
                            pass
                    
                    # Get (extended) city
                    city = f'{addr.get("city", "")} {addr.get("extendedAddress", "")}'.strip()
                    city = city if city else None
                    # Get other details
                    province = addr.get("region", None)
                    postalCode = addr.get("postalCode", None)
                    countryCode = addr.get("countryCode", None)
                    name = addr.get("formattedType", None)
                    # Do not sync empty addresses
                    if not any([street, city, province, postalCode, countryCode]):
                        continue
                    # Name can not be empty
                    name = name if name else "Other"
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
        '''Builds a Google <-> Monica contact id mapping and saves it to the database.'''
        # Initialization
        conflicts = []
        googleContacts = self.google.getContacts(requestSyncToken=True)
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
        monicaContacts = self.monica.getContacts()
        contactCount = len(monicaContacts)
        msg = "Starting sync back..."
        self.log.info(msg)
        print("\n" + msg)

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
                gContactDisplayName = googleContact['names'][0].get("displayName", '')

                # Update database and mapping
                self.database.insertData(googleContact['resourceName'],
                                            monicaContact['id'],
                                            gContactDisplayName,
                                            monicaContact['complete_name'])
                msg = f"'{gContactDisplayName}' ('{googleContact['resourceName']}'): New google contact created (sync back)"
                print("\n" + msg)
                self.log.info(msg)
                self.mapping.update({googleContact['resourceName']: str(monicaContact['id'])})
                msg = f"'{googleContact['resourceName']}' <-> '{monicaContact['id']}': New sync connection added"
                self.log.info(msg)

        if not self.google.createdContacts:
            msg = "No contacts for sync back found"
            self.log.info(msg)
            print("\n" + msg)

        # Finished
        msg = "Sync back finished!"
        self.log.info(msg)
        print("\n" + msg)

    def __printSyncSummary(self) -> None:
        '''Prints a summary of all created and updated contacts.'''
        # To be implemented

    def __createGoogleContact(self, monicaContact: dict) -> dict:
        '''Creates a new Google contact from a given Monica contact and returns it.'''
        # Get names
        firstName = monicaContact['first_name'] if monicaContact['first_name'] else ''
        lastName = monicaContact['last_name'] if monicaContact['last_name'] else ''
        fullName = monicaContact['complete_name']
        middleName = self.__getMonicaMiddleName(firstName, lastName, fullName)

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

        # Get first address if exists
        addresses = monicaContact["addresses"]

        # Get career info if exists
        career = {key: value for key, value in monicaContact['information']["career"].items() if value}

        # Get phone numbers
        phoneNumbers = []  # To be implemented

        # Get email addresses
        emails = []  # To be implemented

        # Get tags/labels and create them if neccessary
        labelIds = [self.google.labelMapping.get(tag['name'], self.google.createLabel(tag['name']))
            for tag in monicaContact["tags"]]

        # Create contact upload form
        form = GoogleContactUploadForm(firstName=firstName, lastName=lastName,
                                       middleName=middleName, birthdate=birthday,
                                       phoneNumbers=phoneNumbers, career=career,
                                       emailAdresses=emails, labelIds=labelIds,
                                       addresses=addresses)

        # Upload contact
        contact = self.google.createContact(data=form.data)

        return contact

    def __getMonicaMiddleName(self, firstName: str, lastName: str, fullName: str) -> str:
        '''Monica contacts have for some reason a hidden field middlename that can be set (creation/update)
        but sadly can not retrieved later. This function computes it by using the complete_name field.'''
        try:
            middleName = fullName[len(firstName):len(fullName) - len(lastName)].strip()
            return middleName
        except:
            return ''

    def __checkDatabaseConsistency(self) -> None:
        '''Checks if there are orphaned database entries which need to be resolved.'''
        # To be implemented

    def __generateFakeId(self, idList: list) -> str:
        '''Used to generate nonsense ids for debugging and testing'''
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
        self.monica.updateContact(id=monicaContact["id"], data=googleForm.data)

    def __getMonicaForm(self, monicaContact: dict) -> MonicaContactUploadForm:
        '''Creates a Monica contact upload form from a given Monica contact for comparison.'''
        # Get names
        firstName = monicaContact['first_name'] if monicaContact['first_name'] else ''
        lastName = monicaContact['last_name'] if monicaContact['last_name'] else ''
        fullName = monicaContact['complete_name']
        middleName = self.__getMonicaMiddleName(firstName, lastName, fullName)

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
            msg = f"'{gContactDisplayName}' ('{monicaContact['id']}'): Conflict resolved: New Monica contact created"
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
        msg = f"'{googleContact['resourceName']}' <-> '{monicaContact['id']}': New sync connection added"
        self.log.info(msg)
        if not resolved:
            print("Conflict resolved: " + msg)
        return str(monicaContact['id'])

    # pylint: disable=unsubscriptable-object
    def __simpleMonicaIdSearch(self, googleContact: dict) -> Union[str, None]:
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

    def __getMonicaNamesFromGoogleContact(self, googleContact: dict) -> Tuple[str, str]:
        '''Creates first and last name from a Google contact with respect to honoric
        suffix/prefix.'''
        givenName = googleContact['names'][0].get("givenName", '')
        familyName = googleContact['names'][0].get("familyName", '')
        prefix = googleContact['names'][0].get("honorificPrefix", '')
        suffix = googleContact['names'][0].get("honorificSuffix", '')
        if prefix:
            givenName = f"{prefix} {givenName}".strip()
        if suffix:
            familyName = f"{familyName} {suffix}".strip()
        return givenName, familyName
