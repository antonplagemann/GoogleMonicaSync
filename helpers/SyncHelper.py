import os
from datetime import datetime
from logging import Logger
from typing import Any, Dict, List, Tuple, Union

from helpers.DatabaseHelper import Database, DatabaseEntry
from helpers.Exceptions import BadUserInput, DatabaseError, UserChoice
from helpers.GoogleHelper import Google, GoogleContactUploadForm
from helpers.MonicaHelper import Monica, MonicaContactUploadForm


class Sync:
    """Handles all syncing and merging issues with Google, Monica and the database."""

    def __init__(
        self,
        log: Logger,
        database_handler: Database,
        monica_handler: Monica,
        google_handler: Google,
        is_sync_back_to_google: bool,
        is_check_database: bool,
        is_delete_monica_contacts_on_sync: bool,
        is_street_reversal_on_address_sync: bool,
        syncing_fields: list,
    ) -> None:
        self.log = log
        self.start_time = datetime.now()
        self.monica = monica_handler
        self.google = google_handler
        self.database = database_handler
        self.mapping = self.database.get_id_mapping()
        self.reverse_mapping = {monica_id: google_id for google_id, monica_id in self.mapping.items()}
        self.next_sync_token = self.database.get_google_next_sync_token()
        self.is_sync_back = is_sync_back_to_google
        self.is_check = is_check_database
        self.is_delete_monica_contacts = is_delete_monica_contacts_on_sync
        self.is_street_reversal = is_street_reversal_on_address_sync
        self.syncing_fields = set(syncing_fields)
        self.skip_creation_prompt = False

    def __update_mapping(self, google_id: str, monica_id: str) -> None:
        """Updates the internal Google <-> Monica id mapping dictionary."""
        self.mapping.update({google_id: monica_id})
        self.reverse_mapping.update({monica_id: google_id})

    def start_sync(self, sync_type: str = "") -> None:
        """Starts the next sync cycle depending on the requested type
        and the database data."""
        if sync_type == "initial":
            # Initial sync requested
            self.__initial_sync()
        elif not self.mapping:
            # There is no sync database. Initial sync is needed for all other sync types
            msg = "No sync database found, please do a initial sync first!"
            self.log.info(msg)
            print(msg + "\n")
            raise BadUserInput("Initial sync needed!")
        elif sync_type == "full":
            # As this is a full sync, get all contacts at once to save time
            self.monica.get_contacts()
            # Full sync requested so dont use database timestamps here
            self.__sync("full", is_date_based_sync=False)
        elif sync_type == "delta" and not self.next_sync_token:
            # Delta sync requested but no sync token found
            msg = "No sync token found, delta sync not possible. Doing (fast) full sync instead..."
            self.log.info(msg)
            print(msg + "\n")
            # Do a full sync with database timestamp comparison (fast)
            self.__sync("full")
        elif sync_type == "delta":
            # Delta sync requested
            self.__sync("delta")
        elif sync_type == "syncBack":
            # Sync back to Google requested
            self.__sync_back()

        # Print statistics
        self.__print_sync_statistics()

        if self.is_check:
            # Database check requested
            self.check_database()

    def __initial_sync(self) -> None:
        """Builds the syncing database and starts a full sync. Needs user interaction!"""
        self.database.delete_and_initialize()
        self.mapping.clear()
        self.__build_sync_database()
        print("\nThe following fields will be overwritten with Google data:")
        for field in self.syncing_fields - {"notes"}:
            print(f"- {field}")
        print("Start full sync now?")
        print("\t0: No (abort initial sync)")
        print("\t1: Yes")
        choice = self.__get_user_input(allowed_nums=[0, 1])
        if not choice:
            raise UserChoice("Sync aborted by user choice")
        self.__sync("full", is_date_based_sync=False)

    def __delete_monica_contact(self, google_contact: dict) -> None:
        """Removes a Monica contact given a corresponding Google contact."""
        try:
            # Initialization
            google_id = google_contact["resourceName"]
            entry = self.database.find_by_id(google_id=google_id)
            if not entry:
                raise DatabaseError(f"No database entry for deleted google contact '{google_id}' found!")

            self.log.info(
                f"'{entry.google_full_name}' ('{google_id}'): "
                "Found deleted Google contact. Removing database entry..."
            )

            # Try to delete the corresponding contact
            if self.is_delete_monica_contacts:
                self.log.info(
                    f"'{entry.monica_full_name}' ('{entry.monica_id}'): Deleting Monica contact..."
                )
                self.monica.delete_contact(entry.monica_id, entry.monica_full_name)
            self.database.delete(google_id, entry.monica_id)
            self.mapping.pop(google_id)
            msg = f"'{entry.google_full_name}' ('{google_id}'): database entry removed successfully"
            self.log.info(msg)
        except Exception:
            name = entry.google_full_name if entry else ""
            msg = f"'{name}' ('{google_id}'): Failed removing Monica contact or database entry!"
            self.log.error(msg)
            print(msg)

    def __sync(self, sync_type: str, is_date_based_sync: bool = True) -> None:
        """Fetches every contact from Google and Monica and does a full sync."""
        # Initialization
        msg = f"Starting {sync_type} sync..."
        self.log.info(msg)
        print("\n" + msg)
        if sync_type == "delta":
            google_contacts = self.google.get_contacts(syncToken=self.next_sync_token)
        else:
            google_contacts = self.google.get_contacts()
        contact_count = len(google_contacts)

        # If Google hasn't returned some data
        if not google_contacts:
            msg = "No (changed) Google contacts found!"
            self.log.info(msg)
            print("\n" + msg)

        # Process every Google contact
        for num, google_contact in enumerate(google_contacts):
            print(f"Processing Google contact {num+1} of {contact_count}")

            # Delete Monica contact if Google contact was deleted (if chosen by user; delta sync only)
            is_deleted = google_contact.get("metadata", {}).get("deleted", False)
            if is_deleted:
                self.__delete_monica_contact(google_contact)
                # Skip further processing
                continue

            entry = self.database.find_by_id(google_id=google_contact["resourceName"])

            # Create a new Google contact in the database if there's nothing yet
            if not entry:
                # Create a new Google contact in the database if there's nothing yet
                google_id = google_contact["resourceName"]
                g_contact_display_name = self.google.get_contact_names(google_contact)[3]
                msg = (
                    f"'{g_contact_display_name}' ('{google_id}'): "
                    "No Monica id found': Creating new Monica contact..."
                )
                self.log.info(msg)
                print("\n" + msg)

                # Create new Monica contact
                monica_contact = self.create_monica_contact(google_contact)
                msg = (
                    f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                    "New Monica contact created"
                )
                self.log.info(msg)
                print(msg)

                # Update database and mapping
                new_database_entry = DatabaseEntry(
                    google_contact["resourceName"],
                    monica_contact["id"],
                    g_contact_display_name,
                    monica_contact["complete_name"],
                    google_contact["metadata"]["sources"][0]["updateTime"],
                    monica_contact["updated_at"],
                )
                self.database.insert_data(new_database_entry)
                self.__update_mapping(google_contact["resourceName"], str(monica_contact["id"]))
                msg = (
                    f"'{google_contact['resourceName']}' <-> '{monica_contact['id']}': "
                    "New sync connection added"
                )
                self.log.info(msg)

                # Sync additional details
                self.__sync_details(google_contact, monica_contact)

                # Proceed with next contact
                continue

            # Skip all contacts which have not changed
            # according to the database lastChanged date (if present)
            contact_timestamp = google_contact["metadata"]["sources"][0]["updateTime"]
            database_date = self.__convert_google_timestamp(entry.google_last_changed)
            contact_date = self.__convert_google_timestamp(contact_timestamp)
            if is_date_based_sync and database_date == contact_date:
                continue

            # Get Monica contact by id
            monica_contact = self.monica.get_contact(entry.monica_id)
            # Merge name, birthday and deceased date and update them
            self.__merge_and_update_nbd(monica_contact, google_contact)

            # Update Google contact last changed date in the database
            google_last_changed = google_contact["metadata"]["sources"][0]["updateTime"]
            updated_entry = DatabaseEntry(
                google_id=google_contact["resourceName"],
                google_full_name=self.google.get_contact_names(google_contact)[3],
                google_last_changed=google_last_changed,
            )
            self.database.update(updated_entry)

            # Refresh Monica data (could have changed)
            monica_contact = self.monica.get_contact(entry.monica_id)

            # Sync additional details
            self.__sync_details(google_contact, monica_contact)

        # Finished
        msg = f"{sync_type.capitalize()} sync finished!"
        self.log.info(msg)
        print("\n" + msg)

        # Sync lonely Monica contacts back to Google if chosen by user
        if self.is_sync_back:
            self.__sync_back()

    def __sync_details(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs additional details, such as company, jobtitle, labels,
        address, phone numbers, emails, notes, contact picture, etc."""
        if "career" in self.syncing_fields:
            # Sync career info
            self.__sync_career_info(google_contact, monica_contact)

        if "address" in self.syncing_fields:
            # Sync address info
            self.__sync_address(google_contact, monica_contact)

        if "phone" in self.syncing_fields or "email" in self.syncing_fields:
            # Sync phone and email
            self.__sync_phone_email(google_contact, monica_contact)

        if "labels" in self.syncing_fields:
            # Sync labels
            self.__sync_labels(google_contact, monica_contact)

        if "notes" in self.syncing_fields:
            # Sync notes if not existent at Monica
            self.__sync_notes(google_contact, monica_contact)

    def __sync_notes(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs Google contact notes if there is no note present at Monica."""
        monica_notes = self.monica.get_notes(monica_contact["id"], monica_contact["complete_name"])
        try:
            identifier = "\n\n*This note is synced from your Google contacts. Do not edit here.*"
            if google_contact.get("biographies", []):
                # Get Google note
                google_note = {
                    "body": google_contact["biographies"][0].get("value", "").strip(),
                    "contact_id": monica_contact["id"],
                    "is_favorited": False,
                }
                # Convert normal newlines to markdown newlines
                google_note["body"] = google_note["body"].replace("\n", "  \n")

                # Update or create the Monica note
                self.__update_or_create_note(monica_notes, google_note, identifier, monica_contact)

            elif monica_notes:
                for monica_note in monica_notes:
                    if identifier in monica_note["body"]:
                        # Found identifier, delete this note
                        self.monica.delete_note(
                            monica_note["id"],
                            monica_note["contact"]["id"],
                            monica_contact["complete_name"],
                        )
                        break

        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error creating Monica note: {str(e)}"
            )
            self.log.warning(msg)

    def __update_or_create_note(
        self,
        monica_notes: List[dict],
        google_note: Dict[str, Any],
        identifier: str,
        monica_contact: dict,
    ) -> None:
        """Updates a note at Monica or creates it if it does not exist"""
        updated = False
        if monica_notes:
            for monica_note in monica_notes:
                if monica_note["body"] == google_note["body"]:
                    # If there is a note with the same content update it and add the identifier
                    google_note["body"] += identifier
                    self.monica.update_note(
                        monica_note["id"], google_note, monica_contact["complete_name"]
                    )
                    updated = True
                    break
                elif identifier in monica_note["body"]:
                    # Found identifier, update this note if changed
                    google_note["body"] += identifier
                    if monica_note["body"] != google_note["body"]:
                        self.monica.update_note(
                            monica_note["id"], google_note, monica_contact["complete_name"]
                        )
                    updated = True
                    break
        if not updated:
            # No note with same content or identifier found so create a new one
            google_note["body"] += identifier
            self.monica.add_note(google_note, monica_contact["complete_name"])

    def __sync_labels(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs Google contact labels/groups/tags."""
        try:
            # Get google labels information
            google_labels = [
                self.google.get_label_name(label["contactGroupMembership"]["contactGroupResourceName"])
                for label in google_contact.get("memberships", [])
            ]

            # Remove tags if not present in Google contact
            remove_list = [
                label["id"] for label in monica_contact["tags"] if label["name"] not in google_labels
            ]
            if remove_list:
                self.monica.remove_tags(
                    {"tags": remove_list}, monica_contact["id"], monica_contact["complete_name"]
                )

            # Update labels if necessary
            monica_labels = [
                label["name"] for label in monica_contact["tags"] if label["name"] in google_labels
            ]
            if sorted(google_labels) != sorted(monica_labels):
                self.monica.add_tags(
                    {"tags": google_labels}, monica_contact["id"], monica_contact["complete_name"]
                )

        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error updating Monica contact labels: {str(e)}"
            )
            self.log.warning(msg)

    def __sync_phone_email(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs phone and email fields."""
        monica_contact_fields = self.monica.get_contact_fields(
            monica_contact["id"], monica_contact["complete_name"]
        )
        if "email" in self.syncing_fields:
            self.__sync_email(google_contact, monica_contact, monica_contact_fields)
        if "phone" in self.syncing_fields:
            self.__sync_phone(google_contact, monica_contact, monica_contact_fields)

    def __sync_email(
        self, google_contact: dict, monica_contact: dict, monica_contact_fields: List[dict]
    ) -> None:
        """Syncs email fields."""
        try:
            # Email processing
            monica_contact_emails = [
                field
                for field in monica_contact_fields
                if field["contact_field_type"]["type"] == "email"
            ]
            google_contact_emails = google_contact.get("emailAddresses", [])

            if not google_contact_emails:
                # There may be only Monica data: Delete emails
                for monica_email in monica_contact_emails:
                    self.monica.delete_contact_field(
                        monica_email["id"], monica_contact["id"], monica_contact["complete_name"]
                    )
                return

            google_emails = [
                {
                    "contact_field_type_id": self.monica.get_contact_field_id("email"),
                    "data": email["value"].strip(),
                    "contact_id": monica_contact["id"],
                }
                for email in google_contact_emails
            ]

            if not monica_contact_emails:
                # There is only Google data: Create emails
                for google_email in google_emails:
                    self.monica.create_contact_field(
                        monica_contact["id"], google_email, monica_contact["complete_name"]
                    )
                return

            # There is Google and Monica data: Check and recreate emails
            for monica_email in monica_contact_emails:
                # Check if there are emails to be deleted
                if monica_email["content"] in [google_email["data"] for google_email in google_emails]:
                    continue
                else:
                    self.monica.delete_contact_field(
                        monica_email["id"], monica_contact["id"], monica_contact["complete_name"]
                    )
            for google_email in google_emails:
                # Check if there are emails to be created
                if google_email["data"] in [
                    monica_email["content"] for monica_email in monica_contact_emails
                ]:
                    continue
                else:
                    self.monica.create_contact_field(
                        monica_contact["id"], google_email, monica_contact["complete_name"]
                    )

        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error updating Monica contact email: {str(e)}"
            )
            self.log.warning(msg)

    def __sync_phone(
        self, google_contact: dict, monica_contact: dict, monica_contact_fields: List[dict]
    ) -> None:
        """Syncs phone fields."""
        try:
            # Phone number processing
            monica_contact_phones = [
                field
                for field in monica_contact_fields
                if field["contact_field_type"]["type"] == "phone"
            ]
            google_contact_phones = google_contact.get("phoneNumbers", [])

            if not google_contact_phones:
                # No Google data: Delete all Monica contact phone numbers
                for monica_phone in monica_contact_phones:
                    self.monica.delete_contact_field(
                        monica_phone["id"], monica_contact["id"], monica_contact["complete_name"]
                    )
                return

            google_phones = [
                {
                    "contact_field_type_id": self.monica.get_contact_field_id("phone"),
                    "data": number["value"].strip(),
                    "contact_id": monica_contact["id"],
                }
                for number in google_contact_phones
            ]
            if not monica_contact_phones:
                # There is only Google data: Create Monica phone numbers
                for google_phone in google_phones:
                    self.monica.create_contact_field(
                        monica_contact["id"], google_phone, monica_contact["complete_name"]
                    )
                return

            # There is Google and Monica data: Check and recreate phone numbers
            for monica_phone in monica_contact_phones:
                # Check if there are phone numbers to be deleted
                if monica_phone["content"] in [google_phone["data"] for google_phone in google_phones]:
                    continue
                else:
                    self.monica.delete_contact_field(
                        monica_phone["id"], monica_contact["id"], monica_contact["complete_name"]
                    )
            for google_phone in google_phones:
                # Check if there are phone numbers to be created
                if google_phone["data"] in [
                    monica_phone["content"] for monica_phone in monica_contact_phones
                ]:
                    continue
                else:
                    self.monica.create_contact_field(
                        monica_contact["id"], google_phone, monica_contact["complete_name"]
                    )

        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error updating Monica contact phone: {str(e)}"
            )
            self.log.warning(msg)

    def __sync_career_info(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs company and job title fields."""
        try:
            is_monica_data_present = bool(
                monica_contact["information"]["career"]["job"]
                or monica_contact["information"]["career"]["company"]
            )
            is_google_data_present = bool(google_contact.get("organizations", False))
            if is_google_data_present or is_monica_data_present:
                # Get google career information
                company = google_contact.get("organizations", [{}])[0].get("name", "").strip()
                department = google_contact.get("organizations", [{}])[0].get("department", "").strip()
                if department:
                    department = f"; {department}"
                job = google_contact.get("organizations", [{}])[0].get("title", None)
                google_data = {
                    "job": job.strip() if job else None,
                    "company": company + department if company or department else None,
                }
                # Get monica career information
                monica_data = {
                    "job": monica_contact["information"]["career"].get("job", None),
                    "company": monica_contact["information"]["career"].get("company", None),
                }

                # Compare and update if necessary
                if google_data != monica_data:
                    self.monica.update_career(monica_contact["id"], google_data)
        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error updating Monica contact career: {str(e)}"
            )
            self.log.warning(msg)

    def __sync_address(self, google_contact: dict, monica_contact: dict) -> None:
        """Syncs all address fields."""
        try:
            google_address_list = self.__get_google_addresses(google_contact, monica_contact["id"])
            monica_address_list = self.__get_monica_addresses(monica_contact)

            if not google_address_list:
                # Delete all Monica addresses
                for element in monica_address_list:
                    for address_id, _ in element.items():
                        self.monica.delete_address(
                            address_id, monica_contact["id"], monica_contact["complete_name"]
                        )
                return

            # Create list for comparison
            monica_plain_address_list = [
                monica_address for item in monica_address_list for monica_address in item.values()
            ]
            # Do a complete comparison
            addresses_are_equal = [
                google_address in monica_plain_address_list for google_address in google_address_list
            ]
            if all(addresses_are_equal):
                # All addresses are equal, nothing to do
                return

            # Delete all Monica addresses and create new ones afterwards
            # Safest way, I don't want to code more deeper comparisons and update functions
            for element in monica_address_list:
                for address_id, _ in element.items():
                    self.monica.delete_address(
                        address_id, monica_contact["id"], monica_contact["complete_name"]
                    )

            # All old Monica data (if existed) have been cleaned now, proceed with address creation
            for google_address in google_address_list:
                self.monica.create_address(google_address, monica_contact["complete_name"])

        except Exception as e:
            msg = (
                f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                f"Error updating Monica addresses: {str(e)}"
            )
            self.log.warning(msg)

    def __get_monica_addresses(self, monica_contact: dict) -> List[dict]:
        """Get all addresses from a Monica contact"""
        if not monica_contact.get("addresses", False):
            return []
        # Get Monica data
        monica_address_list = []
        for addr in monica_contact.get("addresses", []):
            monica_address_list.append(
                {
                    addr["id"]: {
                        "name": addr["name"],
                        "street": addr["street"],
                        "city": addr["city"],
                        "province": addr["province"],
                        "postal_code": addr["postal_code"],
                        "country": addr["country"].get("iso", None) if addr["country"] else None,
                        "contact_id": monica_contact["id"],
                    }
                }
            )
        return monica_address_list

    def __get_google_addresses(self, google_contact: dict, monica_id: str) -> List[dict]:
        """Get all addresses from a Google contact"""
        if not google_contact.get("addresses", False):
            return []
        # Get Google data
        google_address_list = []
        for addr in google_contact.get("addresses", []):
            # None type is important for comparison, empty string won't work here
            name = None
            street = None
            city = None
            province = None
            postal_code = None
            country_code = None
            street = addr.get("streetAddress", "").replace("\n", " ").strip() or None
            if self.is_street_reversal:
                # Street reversal: from '13 Auenweg' to 'Auenweg 13'
                try:
                    if street and street[0].isdigit():
                        street = (f'{street[street.index(" ")+1:]} {street[:street.index(" ")]}').strip()
                except Exception:
                    msg = f"Street reversal failed for '{street}'"
                    self.log.warning(msg)
                    print(msg)

            # Get (extended) city
            city = f'{addr.get("city", "")} {addr.get("extendedAddress", "")}'.strip() or None
            # Get other details
            province = addr.get("region", None)
            postal_code = addr.get("postalCode", None)
            country_code = addr.get("countryCode", None)
            # Name can not be empty
            name = addr.get("formattedType", None) or "Other"
            # Do not sync empty addresses
            if not any([street, city, province, postal_code, country_code]):
                continue
            google_address_list.append(
                {
                    "name": name,
                    "street": street,
                    "city": city,
                    "province": province,
                    "postal_code": postal_code,
                    "country": country_code,
                    "contact_id": monica_id,
                }
            )
        return google_address_list

    def __build_sync_database(self) -> None:
        """Builds a Google <-> Monica 1:1 contact id mapping and saves it to the database."""
        # Initialization
        conflicts = []
        google_contacts = self.google.get_contacts()
        self.monica.get_contacts()
        contact_count = len(google_contacts)
        msg = "Building sync database..."
        self.log.info(msg)
        print("\n" + msg)

        # Process every Google contact
        for num, google_contact in enumerate(google_contacts):
            print(f"Processing Google contact {num+1} of {contact_count}")
            # Try non-interactive search first
            monica_id = self.__simple_monica_id_search(google_contact)
            if not monica_id:
                # Non-interactive search failed, try interactive search next
                conflicts.append(google_contact)

        # Process all conflicts
        if len(conflicts):
            msg = f"Found {len(conflicts)} possible conflicts, starting resolving procedure..."
            self.log.info(msg)
            print("\n" + msg)
        for google_contact in conflicts:
            # Do a interactive search with user interaction next
            monica_id = self.__interactive_monica_id_search(google_contact)
            assert monica_id, "Could not create a Monica contact. Sync aborted."

        # Finished
        msg = "Sync database built!"
        self.log.info(msg)
        print("\n" + msg)

    def __sync_back(self) -> None:
        """Sync lonely Monica contacts back to Google by creating a new contact there."""
        msg = "Starting sync back..."
        self.log.info(msg)
        print("\n" + msg)
        monica_contacts = self.monica.get_contacts()
        contact_count = len(monica_contacts)

        # Process every Monica contact
        for num, monica_contact in enumerate(monica_contacts):
            print(f"Processing Monica contact {num+1} of {contact_count}")

            # If there the id isn't in the database: create a new Google contact and upload
            if str(monica_contact["id"]) not in self.mapping.values():
                # Create Google contact
                google_contact = self.create_google_contact(monica_contact)
                if not google_contact:
                    msg = (
                        f"'{monica_contact['complete_name']}': "
                        "Error encountered at creating new Google contact. Skipping..."
                    )
                    self.log.warning(msg)
                    print(msg)
                    continue
                g_contact_display_name = self.google.get_contact_names(google_contact)[3]

                # Update database and mapping
                database_entry = DatabaseEntry(
                    google_contact["resourceName"],
                    monica_contact["id"],
                    g_contact_display_name,
                    monica_contact["complete_name"],
                )
                self.database.insert_data(database_entry)
                msg = (
                    f"'{g_contact_display_name}' ('{google_contact['resourceName']}'): "
                    "New google contact created (sync back)"
                )
                print("\n" + msg)
                self.log.info(msg)
                self.__update_mapping(google_contact["resourceName"], str(monica_contact["id"]))
                msg = (
                    f"'{google_contact['resourceName']}' <-> '{monica_contact['id']}': "
                    "New sync connection added"
                )
                self.log.info(msg)

        if not self.google.created_contacts:
            msg = "No contacts for sync back found"
            self.log.info(msg)
            print("\n" + msg)

        # Finished
        msg = "Sync back finished!"
        self.log.info(msg)
        print(msg)

    def __print_sync_statistics(self) -> None:
        """Prints and logs a pretty sync statistic of the last sync."""
        self.monica.update_statistics()
        tme = str(datetime.now() - self.start_time).split(".")[0] + "h"
        gac = str(self.google.api_requests) + (8 - len(str(self.google.api_requests))) * " "
        mac = str(self.monica.api_requests) + (8 - len(str(self.monica.api_requests))) * " "
        mcc = (
            str(len(self.monica.created_contacts))
            + (8 - len(str(len(self.monica.created_contacts)))) * " "
        )
        mcu = (
            str(len(self.monica.updated_contacts))
            + (8 - len(str(len(self.monica.updated_contacts)))) * " "
        )
        mcd = (
            str(len(self.monica.deleted_contacts))
            + (8 - len(str(len(self.monica.deleted_contacts)))) * " "
        )
        gcc = (
            str(len(self.google.created_contacts))
            + (8 - len(str(len(self.google.created_contacts)))) * " "
        )
        msg = (
            "\n"
            f"Sync statistics: \n"
            f"+-------------------------------------+\n"
            f"| Syncing time:             {tme   }  |\n"
            f"| Google api calls used:    {gac   }  |\n"
            f"| Monica api calls used:    {mac   }  |\n"
            f"| Monica contacts created:  {mcc   }  |\n"
            f"| Monica contacts updated:  {mcu   }  |\n"
            f"| Monica contacts deleted:  {mcd   }  |\n"
            f"| Google contacts created:  {gcc   }  |\n"
            f"+-------------------------------------+"
        )
        print(msg)
        self.log.info(msg)

    def create_google_contact(self, monica_contact: dict) -> dict:
        """Creates a new Google contact from a given Monica contact and returns it."""
        # Get names (no nickname)
        first_name = monica_contact["first_name"] or ""
        last_name = monica_contact["last_name"] or ""
        full_name = monica_contact["complete_name"] or ""
        nickname = monica_contact["nickname"] or ""
        middle_name = self.__get_monica_middle_name(first_name, last_name, nickname, full_name)

        # Get birthday details (age based birthdays are not supported by Google)
        birthday = {}
        birthday_timestamp = monica_contact["information"]["dates"]["birthdate"]["date"]
        is_age_based = monica_contact["information"]["dates"]["birthdate"]["is_age_based"]
        if birthday_timestamp and not is_age_based:
            is_year_unknown = monica_contact["information"]["dates"]["birthdate"]["is_year_unknown"]
            date = self.__convert_monica_timestamp(birthday_timestamp)
            if not is_year_unknown:
                birthday.update({"year": date.year})
            birthday.update({"month": date.month, "day": date.day})

        # Get addresses
        addresses = monica_contact["addresses"] if "address" in self.syncing_fields else []

        # Get career info if exists
        career = {
            key: value
            for key, value in monica_contact["information"]["career"].items()
            if value and "career" in self.syncing_fields
        }

        # Get phone numbers and email addresses
        if "phone" in self.syncing_fields or "email" in self.syncing_fields:
            monica_contact_fields = self.monica.get_contact_fields(
                monica_contact["id"], monica_contact["complete_name"]
            )
            # Get email addresses
            emails = [
                field["content"]
                for field in monica_contact_fields
                if field["contact_field_type"]["type"] == "email" and "email" in self.syncing_fields
            ]
            # Get phone numbers
            phone_numbers = [
                field["content"]
                for field in monica_contact_fields
                if field["contact_field_type"]["type"] == "phone" and "phone" in self.syncing_fields
            ]

        # Get tags/labels and create them if necessary
        label_ids = [
            self.google.get_label_id(tag["name"])
            for tag in monica_contact["tags"]
            if "labels" in self.syncing_fields
        ]

        # Create contact upload form
        form = GoogleContactUploadForm(
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            birthdate=birthday,
            phone_numbers=phone_numbers,
            career=career,
            email_adresses=emails,
            label_ids=label_ids,
            addresses=addresses,
        )

        # Upload contact
        contact = self.google.create_contact(data=form.get_data())

        return contact

    def __get_monica_middle_name(
        self, first_name: str, last_name: str, nickname: str, full_name: str
    ) -> str:
        """Monica contacts have for some reason a hidden field middlename
        that can be set (creation/update) but sadly can not retrieved later.
        This function computes it by using the complete_name field."""
        try:
            # If there is a nickname it will be parenthesized with a space
            nickname_length = len(nickname) + 3 if nickname else 0
            middle_name = full_name[
                len(first_name) : len(full_name) - (len(last_name) + nickname_length)
            ].strip()
            return middle_name
        except Exception:
            return ""

    def __check_google_contacts(self, google_contacts: List[dict]) -> Tuple[List[dict], int]:
        """Checks every Google contact if it is currently in sync"""
        errors = 0
        google_contacts_not_synced = []
        google_contacts_count = len(google_contacts)
        # Check every Google contact
        for num, google_contact in enumerate(google_contacts):
            print(f"Processing Google contact {num+1} of {google_contacts_count}")

            # Get monica id
            monica_id = self.mapping.get(google_contact["resourceName"], None)
            if not monica_id:
                google_contacts_not_synced.append(google_contact)
                continue

            # Get monica contact
            try:
                monica_contact = self.monica.get_contact(monica_id)
                assert monica_contact
            except Exception:
                errors += 1
                msg = (
                    f"'{self.google.get_contact_names(google_contact)[3]}'"
                    f" ('{google_contact['resourceName']}'): "
                    f"Wrong id or missing Monica contact for id '{monica_id}'."
                )
                self.log.error(msg)
                print("\nError: " + msg)
        return google_contacts_not_synced, errors

    def __check_monica_contacts(self, monica_contacts: List[dict]) -> Tuple[List[dict], int]:
        """Checks every Google contact if it is currently in sync"""
        errors = 0
        monica_contacts_not_synced = []
        monica_contacts_count = len(monica_contacts)
        # Check every Monica contact
        for num, monica_contact in enumerate(monica_contacts):
            print(f"Processing Monica contact {num+1} of {monica_contacts_count}")

            # Get Google id
            google_id = self.reverse_mapping.get(str(monica_contact["id"]), None)
            if not google_id:
                monica_contacts_not_synced.append(monica_contact)
                continue

            # Get Google contact
            try:
                google_contact = self.google.get_contact(google_id)
                assert google_contact
            except Exception:
                errors += 1
                msg = (
                    f"'{monica_contact['complete_name']}' ('{monica_contact['id']}'): "
                    f"Wrong id or missing Google contact for id '{google_id}'."
                )
                self.log.error(msg)
                print("\nError: " + msg)
        return monica_contacts_not_synced, errors

    def __check_results(
        self,
        orphaned_entries: List[str],
        monica_contacts_not_synced: List[dict],
        google_contacts_not_synced: List[dict],
    ) -> None:
        if orphaned_entries:
            self.log.info("The following database entries are orphaned:")
            for google_id in orphaned_entries:
                entry = self.database.find_by_id(google_id)
                if not entry:
                    raise DatabaseError("Database externally modified, entry not found!")
                self.log.info(
                    f"'{google_id}' <-> '{entry.monica_id}' "
                    f"('{entry.google_full_name}' <-> '{entry.monica_full_name}')"
                )
                self.log.info(
                    "This doesn't cause sync errors, but you can fix it doing initial sync '-i'"
                )
        if not monica_contacts_not_synced and not google_contacts_not_synced:
            self.log.info("All contacts are currently in sync")
        elif monica_contacts_not_synced:
            self.log.info("The following Monica contacts are currently not in sync:")
            for monica_contact in monica_contacts_not_synced:
                self.log.info(f"'{monica_contact['complete_name']}' ('{monica_contact['id']}')")
            self.log.info("You can do a sync back '-sb' to fix that")
        if google_contacts_not_synced:
            self.log.info("The following Google contacts are currently not in sync:")
            for google_contact in google_contacts_not_synced:
                google_id = google_contact["resourceName"]
                g_contact_display_name = self.google.get_contact_names(google_contact)[3]
                self.log.info(f"'{g_contact_display_name}' ('{google_id}')")
            self.log.info("You can do a full sync '-f' to fix that")

    def check_database(self) -> None:
        """Checks if there are orphaned database entries which need to be resolved.
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
           -> Warning: orphaned database entry"""
        # Initialization
        start_time = datetime.now()
        errors = 0
        msg = "Starting database check..."
        self.log.info(msg)
        print("\n" + msg)

        # Get contacts
        google_contacts = self.google.get_contacts(refetch_data=True, requestSyncToken=False)
        monica_contacts = self.monica.get_contacts()

        # Check every Google contact
        google_contacts_not_synced, error_count = self.__check_google_contacts(google_contacts)
        errors += error_count

        # Check every Monica contact
        monica_contacts_not_synced, error_count = self.__check_monica_contacts(monica_contacts)
        errors += error_count

        # Check for orphaned database entries
        google_ids = [c["resourceName"] for c in google_contacts]
        monica_ids = [str(c["id"]) for c in monica_contacts]
        orphaned_entries = [
            google_id
            for google_id, monica_id in self.mapping.items()
            if google_id not in google_ids and monica_id not in monica_ids
        ]

        # Log results
        self.__check_results(orphaned_entries, monica_contacts_not_synced, google_contacts_not_synced)

        # Finished
        if errors:
            msg = "Database check failed. Consider doing initial sync '-i' again!"
        else:
            msg = "Database check finished, no critical errors found!"
        msg2 = (
            "If you encounter non-synced contacts on both sides that match each other "
            "you should do an initial sync '-i' again to match them."
        )
        self.log.info(msg)
        self.log.info(msg2)
        print("\n" + msg)
        print(msg2)

        # Print and log statistics
        self.__print_check_statistics(
            start_time,
            errors,
            len(orphaned_entries),
            len(monica_contacts_not_synced),
            len(google_contacts_not_synced),
            len(monica_contacts),
            len(google_contacts),
        )

    def __print_check_statistics(
        self,
        start_time: datetime,
        errors: int,
        orphaned: int,
        monica_contacts_not_synced: int,
        google_contacts_not_synced: int,
        monica_contacts: int,
        google_contacts: int,
    ) -> None:
        """Prints and logs a pretty check statistic of the last database check."""
        tme = str(datetime.now() - start_time).split(".")[0] + "h"
        err = str(errors) + (8 - len(str(errors))) * " "
        oph = str(orphaned) + (8 - len(str(orphaned))) * " "
        mns = str(monica_contacts_not_synced) + (8 - len(str(monica_contacts_not_synced))) * " "
        gns = str(google_contacts_not_synced) + (8 - len(str(google_contacts_not_synced))) * " "
        cmc = str(monica_contacts) + (8 - len(str(monica_contacts))) * " "
        cgc = str(google_contacts) + (8 - len(str(google_contacts))) * " "
        msg = (
            "\n"
            f"Check statistics: \n"
            f"+-----------------------------------------+\n"
            f"| Check time:                   {tme   }  |\n"
            f"| Errors:                       {err   }  |\n"
            f"| Orphaned database entries:    {oph   }  |\n"
            f"| Monica contacts not in sync:  {mns   }  |\n"
            f"| Google contacts not in sync:  {gns   }  |\n"
            f"| Checked Monica contacts:      {cmc   }  |\n"
            f"| Checked Google contacts:      {cgc   }  |\n"
            f"+-----------------------------------------+"
        )
        print(msg)
        self.log.info(msg)

    def __merge_and_update_nbd(self, monica_contact: dict, google_contact: dict) -> None:
        """Updates names, birthday and deceased date by merging an existing Monica contact with
        a given Google contact."""
        # Get names
        names_and_birthday = self.__get_monica_details(google_contact)

        # Get deceased info
        deceased_date = monica_contact["information"]["dates"]["deceased_date"]["date"]
        is_d_date_age_based = monica_contact["information"]["dates"]["deceased_date"]["is_age_based"]
        deceased_year, deceased_month, deceased_day = None, None, None
        if deceased_date:
            date = self.__convert_monica_timestamp(deceased_date)
            deceased_year = date.year
            deceased_month = date.month
            deceased_day = date.day

        # Assemble form object
        google_form = MonicaContactUploadForm(
            **names_and_birthday,
            is_deceased=monica_contact["is_dead"],
            is_deceased_date_known=bool(deceased_date),
            deceased_year=deceased_year,
            deceased_month=deceased_month,
            deceased_day=deceased_day,
            deceased_age_based=is_d_date_age_based,
        )

        # Check if contacts are already equal
        monica_form = self.__get_monica_form(monica_contact)
        if google_form.data == monica_form.data:
            return

        # Upload contact
        self.monica.update_contact(monica_id=monica_contact["id"], data=google_form.data)

    def __get_monica_form(self, monica_contact: dict) -> MonicaContactUploadForm:
        """Creates a Monica contact upload form from a given Monica contact for comparison."""
        # Get names
        first_name = monica_contact["first_name"] or ""
        last_name = monica_contact["last_name"] or ""
        full_name = monica_contact["complete_name"] or ""
        nickname = monica_contact["nickname"] or ""
        middle_name = self.__get_monica_middle_name(first_name, last_name, nickname, full_name)

        # Get birthday details
        birthday_timestamp = monica_contact["information"]["dates"]["birthdate"]["date"]
        birthdate_year, birthdate_month, birthdate_day = None, None, None
        if birthday_timestamp:
            is_year_unknown = monica_contact["information"]["dates"]["birthdate"]["is_year_unknown"]
            date = self.__convert_monica_timestamp(birthday_timestamp)
            birthdate_year = date.year if not is_year_unknown else None
            birthdate_month = date.month
            birthdate_day = date.day

        # Get deceased info
        deceased_date = monica_contact["information"]["dates"]["deceased_date"]["date"]
        is_d_date_age_based = monica_contact["information"]["dates"]["deceased_date"]["is_age_based"]
        deceased_year, deceased_month, deceased_day = None, None, None
        if deceased_date:
            date = self.__convert_monica_timestamp(deceased_date)
            deceased_year = date.year
            deceased_month = date.month
            deceased_day = date.day

        # Assemble form object
        return MonicaContactUploadForm(
            first_name=first_name,
            monica=self.monica,
            last_name=last_name,
            nick_name=nickname,
            middle_name=middle_name,
            gender_type=monica_contact["gender_type"],
            birthdate_day=birthdate_day,
            birthdate_month=birthdate_month,
            birthdate_year=birthdate_year,
            is_birthdate_known=bool(birthday_timestamp),
            is_deceased=monica_contact["is_dead"],
            is_deceased_date_known=bool(deceased_date),
            deceased_year=deceased_year,
            deceased_month=deceased_month,
            deceased_day=deceased_day,
            deceased_age_based=is_d_date_age_based,
            create_reminders=self.monica.create_reminders,
        )

    def create_monica_contact(self, google_contact: dict) -> dict:
        """Creates a new Monica contact from a given Google contact and returns it."""
        form_data = self.__get_monica_details(google_contact)

        # Assemble form object
        form = MonicaContactUploadForm(**form_data)
        # Upload contact
        monica_contact = self.monica.create_contact(
            data=form.data, reference_id=google_contact["resourceName"]
        )
        return monica_contact

    def __get_monica_details(self, google_contact: dict) -> Dict[str, Any]:
        # Get names
        first_name, last_name = self.__get_monica_names_from_google_contact(google_contact)
        middle_name = self.google.get_contact_names(google_contact)[1]
        display_name = self.google.get_contact_names(google_contact)[3]
        nickname = self.google.get_contact_names(google_contact)[6]
        # First name is required for Monica
        if not first_name:
            first_name = display_name
            last_name = ""

        # Get birthday
        birthday = google_contact.get("birthdays", None)
        birthdate_year, birthdate_month, birthdate_day = None, None, None
        if birthday:
            birthdate_year = birthday[0].get("date", {}).get("year", None)
            birthdate_month = birthday[0].get("date", {}).get("month", None)
            birthdate_day = birthday[0].get("date", {}).get("day", None)
        is_birthdate_known = all([birthdate_month, birthdate_day])

        form_data = {
            "first_name": first_name,
            "monica": self.monica,
            "last_name": last_name,
            "middle_name": middle_name,
            "nick_name": nickname,
            "birthdate_day": birthdate_day if is_birthdate_known else None,
            "birthdate_month": birthdate_month if is_birthdate_known else None,
            "birthdate_year": birthdate_year if is_birthdate_known else None,
            "is_birthdate_known": all([birthdate_month, birthdate_day]),
            "create_reminders": self.monica.create_reminders,
        }
        return form_data

    def __convert_google_timestamp(self, timestamp: str) -> Union[datetime, None]:
        """Converts Google timestamp to a datetime object."""
        try:
            return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            return None

    def __convert_monica_timestamp(self, timestamp: str) -> datetime:
        """Converts Monica timestamp to a datetime object."""
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    def __interactive_monica_id_search(self, google_contact: dict) -> str:
        """Advanced search by first and last name for a given Google contact.
        Tries to find a matching Monica contact and asks for user choice if
        at least one candidate has been found. Creates a new Monica contact
        if necessary or chosen by User. Returns Monica contact id."""
        # Initialization
        candidates = []
        g_contact_given_name = self.google.get_contact_names(google_contact)[0]
        g_contact_family_name = self.google.get_contact_names(google_contact)[2]
        g_contact_display_name = self.google.get_contact_names(google_contact)[3]
        monica_contact = None

        # Process every Monica contact
        for monica_contact in self.monica.get_contacts():
            contact_in_database = str(monica_contact["id"]) in self.mapping.values()
            is_name_match = (
                g_contact_given_name == monica_contact["first_name"]
                or g_contact_family_name == monica_contact["last_name"]
            )
            if not contact_in_database and is_name_match:
                # If the id isn't in the database and first or last name matches
                # add potential candidate to list
                candidates.append(monica_contact)

        # If there is at least one candidate let the user choose
        choice = None
        if candidates:
            print("\nPossible syncing conflict, please choose your alternative by number:")
            print(f"\tWhich Monica contact should be connected to '{g_contact_display_name}'?")
            for num, monica_contact in enumerate(candidates):
                print(f"\t{num+1}: {monica_contact['complete_name']}")
            print(f"\t{num+2}: Create a new Monica contact")
            choice = self.__get_user_input(allowed_nums=list(range(1, len(candidates) + 2)))
            # Created a sublist with the selected candidate
            # or an empty list if user votes for a new contact
            candidates = candidates[choice - 1 : choice]

        # No candidates found, let the user choose to create a new contact
        elif not self.skip_creation_prompt:
            print(f"\nNo Monica contact has been found for '{g_contact_display_name}'")
            print("\tCreate a new Monica contact?")
            print("\t0: No (abort initial sync)")
            print("\t1: Yes")
            print("\t2: Yes to all")
            choice = choice = self.__get_user_input(allowed_nums=[0, 1, 2])
            if choice == 0:
                raise UserChoice("Sync aborted by user choice")
            if choice == 2:
                # Skip further contact creation prompts
                self.skip_creation_prompt = True

        # If there are no candidates (user vote or nothing found) create a new Monica contact
        if not candidates:
            # Create new Monica contact
            monica_contact = self.create_monica_contact(google_contact)

            # Print success
            msg = f"'{g_contact_display_name}' ('{monica_contact['id']}'): New Monica contact created"
            self.log.info(msg)
            print("Conflict resolved: " + msg)

        # There must be exactly one candidate from user vote
        else:
            monica_contact = candidates[0]

        # Update database and mapping
        database_entry = DatabaseEntry(
            google_contact["resourceName"],
            monica_contact["id"],
            g_contact_display_name,
            monica_contact["complete_name"],
        )
        self.database.insert_data(database_entry)
        self.__update_mapping(google_contact["resourceName"], str(monica_contact["id"]))

        # Print success
        msg = (
            f"'{google_contact['resourceName']}' <-> '{monica_contact['id']}': "
            "New sync connection added"
        )
        self.log.info(msg)
        print("Conflict resolved: " + msg)

        return str(monica_contact["id"])

    def __get_user_input(self, allowed_nums: List[int]) -> int:
        """Prompts for a number entered by the user"""
        # If running from GitHub Actions always choose 1
        if os.getenv("CI", 0):
            print("Running from CI -> 1")
            return 1
        while True:
            try:
                choice = int(input("Enter your choice (number only): "))
                if choice in allowed_nums:
                    return choice
                else:
                    raise BadUserInput()
            except Exception:
                print("Bad input, please try again!\n")

    def __simple_monica_id_search(self, google_contact: dict) -> Union[str, None]:
        """Simple search by displayname for a given Google contact.
        Tries to find a matching Monica contact and returns its id or None if not found"""
        # Initialization
        g_contact_given_name = self.google.get_contact_names(google_contact)[0]
        g_contact_middle_name = self.google.get_contact_names(google_contact)[1]
        g_contact_family_name = self.google.get_contact_names(google_contact)[2]
        g_contact_display_name = self.google.get_contact_names(google_contact)[3]
        candidates = []

        # Process every Monica contact
        for monica_contact in self.monica.get_contacts():
            # Get monica data
            m_contact_id = str(monica_contact["id"])
            m_contact_first_name = monica_contact["first_name"] or ""
            m_contact_last_name = monica_contact["last_name"] or ""
            m_contact_full_name = monica_contact["complete_name"] or ""
            m_contact_nickname = monica_contact["nickname"] or ""
            m_contact_middle_name = self.__get_monica_middle_name(
                m_contact_first_name, m_contact_last_name, m_contact_nickname, m_contact_full_name
            )
            # Check if the Monica contact is already assigned to a Google contact
            is_monica_contact_assigned = m_contact_id in self.mapping.values()
            # Check if display names match
            is_display_name_match = g_contact_display_name == m_contact_full_name
            # Pre-check that the Google contact has a given and a family name
            has_names = g_contact_given_name and g_contact_family_name
            # Check if names match when ignoring honorifix prefixes
            is_without_prefix_match = has_names and (
                " ".join([g_contact_given_name, g_contact_family_name]) == m_contact_full_name
            )
            # Check if first, middle and last name matches
            is_first_last_middle_name_match = (
                m_contact_first_name == g_contact_given_name
                and m_contact_middle_name == g_contact_middle_name
                and m_contact_last_name == g_contact_family_name
            )
            # Assemble all conditions
            matches = [is_display_name_match, is_without_prefix_match, is_first_last_middle_name_match]
            if not is_monica_contact_assigned and any(matches):
                # Add possible candidate
                candidates.append(monica_contact)

        # If there is only one candidate
        if len(candidates) == 1:
            monica_contact = candidates[0]

            # Update database and mapping
            database_entry = DatabaseEntry(
                google_contact["resourceName"],
                monica_contact["id"],
                g_contact_display_name,
                monica_contact["complete_name"],
            )
            self.database.insert_data(database_entry)
            self.__update_mapping(google_contact["resourceName"], str(monica_contact["id"]))
            return str(monica_contact["id"])

        # Simple search failed
        return None

    def __get_monica_names_from_google_contact(self, google_contact: dict) -> Tuple[str, str]:
        """Creates first and last name from a Google contact with respect to honoric
        suffix/prefix."""
        given_name, _, family_name, _, prefix, suffix, _ = self.google.get_contact_names(google_contact)
        if prefix:
            given_name = f"{prefix} {given_name}".strip()
        if suffix:
            family_name = f"{family_name} {suffix}".strip()
        return given_name, family_name
