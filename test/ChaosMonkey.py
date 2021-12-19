from __future__ import annotations

import argparse
import inspect
import logging
import os
import pickle
import random
import sys
from copy import deepcopy
from os.path import join
from time import sleep
from typing import Dict, List

# Include parent folder in module search
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))  # type: ignore
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from dotenv import dotenv_values, find_dotenv  # type: ignore

from helpers.ConfigHelper import Config
from helpers.DatabaseHelper import Database, DatabaseEntry
from helpers.GoogleHelper import Google
from helpers.MonicaHelper import Monica
from helpers.SyncHelper import Sync

LOG_FOLDER = "logs"
LOG_FILENAME = "monkey.log"
STATE_FILENAME = "monkeyState.pickle"
DEFAULT_CONFIG_FILEPATH = join("..", "helpers", ".env.default")
SLEEP_TIME = 0
MOFIFY_COUNT = 4

# Chaos monkey
# Creates, deletes and updates some random contacts at Google and Monica


class State:
    """Maintains the monkey state"""

    def __init__(self, google_contacts: List[dict], seed: int) -> None:
        self.contacts = google_contacts
        self.seed = seed
        self.original_contacts: Dict[str, dict] = {}
        self.deleted_contacts: List[dict] = []
        self.created_contacts: List[dict] = []
        self.deleted_database_entries: List[DatabaseEntry] = []
        self.created_database_entries: List[DatabaseEntry] = []

    def save(self, log: logging.Logger) -> None:
        """Saves the state to the filesystem"""
        with open(STATE_FILENAME, "wb") as state_file:
            pickle.dump(self, state_file)
        self.log(log, "State saved: \n")

    def log(self, log: logging.Logger, title: str) -> None:
        """Logs the current state"""
        log.info(
            title + f"contacts = {len(self.contacts)}\n"
            f"seed = {self.seed}\n"
            f"updated_contacts = {len(self.original_contacts)}\n"
            f"deleted_contacts = {len(self.deleted_contacts)}\n"
            f"created_contacts = {len(self.created_contacts)}\n"
            f"deleted_database_entries = {len(self.deleted_database_entries)}\n"
            f"created_database_entries = {len(self.created_database_entries)}"
        )

    @staticmethod
    def load(monkey: Monkey) -> State:
        """Loads the state from filesystem or creates a new one"""
        if os.path.exists(STATE_FILENAME):
            with open(STATE_FILENAME, "rb") as state_file:
                state: State = pickle.load(state_file)
            state.log(monkey.log, "State loaded: \n")
            return state
        else:
            google_contacts = monkey.google.get_contacts()
            seed = monkey.args.seed
            if not seed:
                seed = random.randint(100000, 999999)  # nosec
            state = State(google_contacts, seed)
            state.log(monkey.log, "State created: \n")
            return state


class Monkey:
    """Main monkey class for producing chaos"""

    def __init__(self) -> None:
        self.fields = [
            "names",
            "birthdays",
            "addresses",
            "emailAddresses",
            "phoneNumbers",
            "biographies",
            "organizations",
            "occupations",
            "memberships",
        ]

    def main(self) -> None:
        try:
            # Create logger
            self.__create_logger()
            self.log.info("Script started")

            # Create argument parser
            self.__create_argument_parser()

            # Load config
            self.__load_config()

            # Create sync object
            self.__create_sync_helper()

            # Load state
            self.state = State.load(self)

            # Set random seed
            random.seed(self.state.seed)
            self.log.info(f"Using random seed '{self.state.seed}'")

            # Start
            if self.args.initial:
                # Start initial sync  (-i)
                self.log.info("Starting initial sync chaos")
                self.initial_chaos(MOFIFY_COUNT)
            elif self.args.delta:
                # Start initial sync  (-d)
                self.log.info("Starting delta sync chaos")
                self.delta_chaos(MOFIFY_COUNT)
            elif self.args.full:
                # Start initial sync  (-f)
                self.log.info("Starting full sync chaos")
                self.full_chaos(MOFIFY_COUNT)
            elif self.args.syncback:
                # Start sync back from Monica to Google  (-sb)
                self.log.info("Starting sync back chaos")
                self.syncback_chaos(MOFIFY_COUNT)
            elif self.args.check:
                # Start database error check  (-c)
                self.log.info("Starting database check chaos")
                self.database_chaos(MOFIFY_COUNT)
            elif self.args.restore:
                # Start database error check  (-c)
                self.log.info("Starting restore Google contacts")
                self.restore_contacts()
            else:
                # Wrong arguments
                self.log.info("Unknown sync arguments, check your input!")
                self.parser.print_help()
                sys.exit(2)

            # Its over now
            self.state.save(self.log)
            # Give the People API some time to process changes before continuing
            self.log.info(f"Waiting {SLEEP_TIME} seconds...")
            sleep(SLEEP_TIME)
            self.log.info("Script ended\n")

        except Exception as e:
            self.log.exception(e)
            self.log.info("Script aborted")
            raise SystemExit(1) from e

    def __get_random_contacts(self, num: int) -> List[dict]:
        """Returns the specified number of random Google contacts"""
        random_indices = random.sample(range(len(self.state.contacts)), num)  # nosec
        return [deepcopy(self.state.contacts[index]) for index in random_indices]

    def __get_random_fields(self, num: int) -> List[str]:
        """Returns the specified number of random Google contact fields"""
        random.shuffle(self.fields)
        assert num <= len(self.fields), f"Not enough fields! ({num})"
        return [self.fields[i] for i in range(num)]

    def __clean_metadata(self, contacts: List[dict]) -> None:
        """Delete all metadata entries from a given Google contact"""
        for contact in contacts:
            del contact["resourceName"]
            del contact["etag"]
            del contact["metadata"]
            for key in tuple(contact):
                if not isinstance(contact[key], list):
                    continue
                for entry in contact[key]:
                    del entry["metadata"]

    def __remove_contacts_from_list(self, contacts: List[dict]) -> None:
        """Removes a contact from the list (.remove does not work because of deepcopies)"""
        delete_resource_names = [contact["resourceName"] for contact in contacts]
        self.state.contacts = [
            contact
            for contact in self.state.contacts
            if contact["resourceName"] not in delete_resource_names
        ]

    def __update_contacts(self, num: int) -> List[dict]:
        """Updates random target Google contacts based on random source contacts.
        Returns the source contacts (not the updated ones)"""
        # Chose random contacts and generate contact pairs
        contacts = self.__get_random_contacts(num * 2)
        contacts_to_update = contacts[:num]
        contacts_to_copy_from = contacts[num:]

        # Update two contacts
        update_list = []
        original_contacts = deepcopy(contacts_to_update)
        self.__remove_contacts_from_list(contacts_to_update)
        for contact_to_update, contact_to_copy_from in zip(contacts_to_update, contacts_to_copy_from):
            # Update fields
            fields = self.__get_random_fields(random.randint(1, 9))  # nosec
            self.log.info(
                f"Updating '{','.join(fields)}' on "
                f"'{contact_to_update['names'][0]['displayName']}' "
                f"('{contact_to_update['resourceName']}')"
            )
            for field in fields:
                contact_to_update[field] = deepcopy(contact_to_copy_from.get(field, []))
                for entry in contact_to_update[field]:
                    del entry["metadata"]

            # Delete other fields
            for key in tuple(contact_to_update):
                if isinstance(contact_to_update[key], list) and key not in self.fields:
                    del contact_to_update[key]

            # Update contact
            update_list.append(contact_to_update)

        # Update contacts
        updated_contacts = self.google.update_contacts(update_list)
        self.state.contacts += updated_contacts
        # Save original contacts to state
        for contact in original_contacts:
            if not self.state.original_contacts.get(contact["resourceName"], None):
                self.state.original_contacts[contact["resourceName"]] = contact

        # Return source contacts
        return contacts_to_copy_from

    def initial_chaos(self, num: int) -> None:
        """Creates Monica contacts.
        Produces some easy and some more complex contact matching cases for initial sync"""
        # Generate easy matches with no changes
        self.__initial_create_easy_matches(num)

        # Generate complex matches by swapping first names
        self.__initial_create_complex_matches(num)

    def __initial_create_complex_matches(self, num: int) -> None:
        """Creates the given contact count at Monica without changes."""
        contacts = self.__get_random_contacts(num)
        contacts_rotated = contacts[1:] + contacts[0:1]
        for i in range(len(contacts)):
            contacts[i]["names"][0]["givenName"] = deepcopy(contacts_rotated[i]["names"][0]["givenName"])
            self.sync.create_monica_contact(contacts[i])

    def __initial_create_easy_matches(self, num: int) -> None:
        """Creates the given contact count at Monica without changes."""
        for contact in self.__get_random_contacts(num):
            self.sync.create_monica_contact(contact)

    def delta_chaos(self, num: int) -> None:
        """Updates two and deletes two Google contacts"""
        # Update random contacts and delete their used source contacts
        contacts = self.__update_contacts(num)
        delete_mapping = {
            contact["resourceName"]: contact["names"][0]["displayName"] for contact in contacts
        }
        self.google.delete_contacts(delete_mapping)
        self.__remove_contacts_from_list(contacts)
        self.state.deleted_contacts += contacts

    def full_chaos(self, num: int) -> None:
        """Updates two and creates two Google contacts"""
        # Update random contacts and recreate their used source contacts
        contacts = self.__update_contacts(num)
        # Clean metadata and id
        self.__clean_metadata(contacts)
        # Create contact
        created_contacts = self.google.create_contacts(contacts)
        self.state.contacts += created_contacts
        self.state.created_contacts += created_contacts

    def syncback_chaos(self, num: int) -> None:
        """Creates two Monica-only contacts for syncback"""
        # Create random Monica contacts
        for contact in self.__get_random_contacts(num):
            self.sync.create_monica_contact(contact)

    def database_chaos(self, num: int) -> None:
        """Deletes two database entries and creates two imaginary ones"""
        # Delete entries
        for contact in self.__get_random_contacts(num):
            existing_entry = self.database.find_by_id(google_id=contact["resourceName"])
            assert existing_entry, f"No entry for {contact['resourceName']} found!"
            self.database.delete(existing_entry.google_id, existing_entry.monica_id)
            self.state.deleted_database_entries.append(existing_entry)
            self.log.info(
                f"Removed '{contact['resourceName']}' "
                f"('{contact['names'][0]['displayName']} from database')"
            )

        # Create random entries
        for num in range(1, num + 1):
            new_entry = DatabaseEntry(f"google/randomEntry{num}", f"monica/randomEntry{num}")
            self.database.insert_data(new_entry)
            self.state.created_database_entries.append(new_entry)
            self.log.info(f"Inserted 'google/randomEntry{num}' into database")

    def restore_contacts(self) -> None:
        """Restore all manipulated Google contacts"""
        # Revert updated contacts
        changed_contacts = [
            contact
            for contact in self.state.contacts
            if contact["resourceName"] in self.state.original_contacts
        ]
        self.__remove_contacts_from_list(list(self.state.original_contacts.values()))
        update_mapping = [
            (original_contact, changed_contact)
            for original_contact in self.state.original_contacts.values()
            for changed_contact in changed_contacts
            if original_contact["resourceName"] == changed_contact["resourceName"]
        ]
        updated_contacts = []
        for original_contact, changed_contact in update_mapping:
            # Revert changes
            for key in tuple(original_contact):
                if not isinstance(original_contact[key], list):
                    continue
                changed_contact[key] = original_contact[key]
            # Delete other fields
            for key in tuple(changed_contact):
                if isinstance(changed_contact[key], list) and key not in self.fields:
                    del changed_contact[key]
            # Update contact
            updated_contacts.append(changed_contact)
        self.state.contacts += updated_contacts
        self.google.update_contacts(updated_contacts)
        self.state.original_contacts = {}

        # Delete created contacts
        delete_mapping = {
            contact["resourceName"]: contact["names"][0]["displayName"]
            for contact in self.state.created_contacts
        }
        self.google.delete_contacts(delete_mapping)
        self.__remove_contacts_from_list(self.state.created_contacts)
        self.state.created_contacts = []

        # Create deleted contacts
        self.__clean_metadata(self.state.deleted_contacts)
        # Create contact
        created_contacts = self.google.create_contacts(self.state.deleted_contacts)
        self.state.contacts += created_contacts
        self.state.deleted_contacts = []

        # Create deleted database entries
        for entry in self.state.deleted_database_entries:
            self.database.insert_data(entry)

        # Delete created database entries
        for entry in self.state.created_database_entries:
            self.database.delete(entry.google_id, entry.monica_id)

    def __create_logger(self) -> None:
        """Creates the logger object"""
        # Set logging configuration
        if not os.path.exists(LOG_FOLDER):
            os.makedirs(LOG_FOLDER)
        log = logging.getLogger("monkey")
        dotenv_log = logging.getLogger("dotenv.main")
        log.setLevel(logging.INFO)
        logging_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        log_filepath = join(LOG_FOLDER, LOG_FILENAME)
        handler = logging.FileHandler(filename=log_filepath, mode="a", encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging_format)
        log.addHandler(logging.StreamHandler(sys.stdout))
        log.addHandler(handler)
        dotenv_log.addHandler(handler)
        self.log = log

    def __create_argument_parser(self) -> None:
        """Creates the argument parser object"""
        # Setup argument parser
        parser = argparse.ArgumentParser(description="Syncs Google contacts to a Monica instance.")
        parser.add_argument(
            "-i",
            "--initial",
            action="store_true",
            required=False,
            help="produce two easy and two more complex contact matching cases for initial sync",
        )
        parser.add_argument(
            "-d",
            "--delta",
            action="store_true",
            required=False,
            help="update two and delete two Google contacts",
        )
        parser.add_argument(
            "-f",
            "--full",
            action="store_true",
            required=False,
            help="update two and create two Google contacts",
        )
        parser.add_argument(
            "-sb",
            "--syncback",
            action="store_true",
            required=False,
            help="create two Monica-only contacts for syncback",
        )
        parser.add_argument(
            "-c",
            "--check",
            action="store_true",
            required=False,
            help="delete two database entries and create two imaginary ones",
        )
        parser.add_argument(
            "-r",
            "--restore",
            action="store_true",
            required=False,
            help="recreate deleted Google contacts",
        )
        parser.add_argument(
            "-s", "--seed", type=int, required=False, help="custom seed for the random generator"
        )

        # Parse arguments
        self.parser = parser
        self.args = parser.parse_args()

    def __load_config(self) -> None:
        """Loads the config from file or environment variables"""
        # Load raw config
        default_config = find_dotenv(DEFAULT_CONFIG_FILEPATH, raise_error_if_not_found=True)
        self.log.info(f"Loading default config from {default_config}")
        default_config_values = dotenv_values(default_config)

        # Load user config from environment vars
        self.log.info("Loading user config from os environment")
        user_config_values = dict(os.environ)
        self.log.info("Config loading complete")
        raw_config = {**default_config_values, **user_config_values}

        # Parse config
        self.conf = Config(self.log, raw_config)
        self.log.info("Config successfully parsed")

    def __create_sync_helper(self) -> None:
        """Creates the main sync class object"""
        # Create sync objects
        self.database = Database(self.log, self.conf.DATABASE_FILE)
        self.google = Google(
            self.log,
            self.database,
            self.conf.GOOGLE_CREDENTIALS_FILE,
            self.conf.GOOGLE_TOKEN_FILE,
            self.conf.GOOGLE_LABELS_INCLUDE,
            self.conf.GOOGLE_LABELS_EXCLUDE,
            self.args.initial,
        )
        self.monica = Monica(
            self.log,
            self.database,
            self.conf.TOKEN,
            self.conf.BASE_URL,
            self.conf.CREATE_REMINDERS,
            self.conf.MONICA_LABELS_INCLUDE,
            self.conf.MONICA_LABELS_EXCLUDE,
        )
        self.sync = Sync(
            self.log,
            self.database,
            self.monica,
            self.google,
            self.args.syncback,
            self.args.check,
            self.conf.DELETE_ON_SYNC,
            self.conf.STREET_REVERSAL,
            self.conf.FIELDS,
        )


if __name__ == "__main__":
    Monkey().main()
