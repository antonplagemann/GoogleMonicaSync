import argparse
import logging
import os
import sys
from os.path import abspath, join

from dotenv import dotenv_values, find_dotenv  # type: ignore

from ConfigHelper import Config
from DatabaseHelper import Database
from Exceptions import ConfigError
from GoogleHelper import Google
from MonicaHelper import Monica
from SyncHelper import Sync

LOG_FOLDER = "logs"
LOG_FILENAME = "chaos.log"
DEFAULT_CONFIG_FILEPATH = ".env.default"
# Chaosmonkey
# Creates, deletes and updates some random contacts at Google and Monica


class Chaos:
    def main(self) -> None:
        try:
            # Create logger
            self.create_logger()
            self.log.info("Script started")

            # Create argument parser
            self.create_argument_parser()

            # Load config
            self.load_config()

            # Create sync object
            self.create_sync_helper()

            # Print chosen sync arguments (optional ones first)
            print("\nYour choice (unordered):")
            if self.args.syncback:
                print("- sync back")
            if self.args.check:
                print("- database check")

            # Start
            if self.args.initial:
                # Start initial sync  (-i)
                print("- initial sync\n")
                self.sync.start_sync("initial")
            elif self.args.delta:
                # Start initial sync  (-d)
                print("- delta sync\n")
                self.sync.start_sync("delta")
            elif self.args.full:
                # Start initial sync  (-f)
                print("- full sync\n")
                self.sync.start_sync("full")
            elif self.args.syncback:
                # Start sync back from Monica to Google  (-sb)
                print("")
                self.sync.start_sync("syncBack")
            elif self.args.check:
                # Start database error check  (-c)
                print("")
                self.sync.check_database()
            elif not self.args.update:
                # Wrong arguments
                print("Unknown sync arguments, check your input!\n")
                self.parser.print_help()
                sys.exit(2)

            # Its over now
            self.log.info("Script ended\n")

        except Exception as e:
            self.log.exception(e)
            self.log.info("Script aborted")
            print(f"\nScript aborted: {type(e).__name__}: {str(e)}")
            print(f"See log file ({join(LOG_FOLDER, LOG_FILENAME)}) for all details")
            raise SystemExit(1) from e

    def create_logger(self) -> None:
        """Creates the logger object"""
        # Set logging configuration
        if not os.path.exists(LOG_FOLDER):
            os.makedirs(LOG_FOLDER)
        log = logging.getLogger("chaos")
        dotenv_log = logging.getLogger("dotenv.main")
        log.setLevel(logging.INFO)
        logging_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        log_filepath = join(LOG_FOLDER, LOG_FILENAME)
        handler = logging.FileHandler(filename=log_filepath, mode="a", encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging_format)
        log.addHandler(handler)
        dotenv_log.addHandler(handler)
        self.log = log

    def create_argument_parser(self) -> None:
        """Creates the argument parser object"""
        # Setup argument parser
        parser = argparse.ArgumentParser(description="Syncs Google contacts to a Monica instance.")
        parser.add_argument(
            "-i",
            "--initial",
            action="store_true",
            required=False,
            help="produce some easy and some more complex contact matching cases for initial sync",
        )
        parser.add_argument(
            "-sb",
            "--syncback",
            action="store_true",
            required=False,
            help="create a few Monica-only contacts for syncback",
        )
        parser.add_argument(
            "-d",
            "--delta",
            action="store_true",
            required=False,
            help="update and delete some Google contacts",
        )
        parser.add_argument(
            "-f",
            "--full",
            action="store_true",
            required=False,
            help="update and create some Google contacts",
        )
        parser.add_argument(
            "-r",
            "--reset",
            action="store_true",
            required=False,
            help="reset all Google contacts to its initial state",
        )

        # Parse arguments
        self.parser = parser
        self.args = parser.parse_args()

    def load_config(self) -> None:
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

    def create_sync_helper(self) -> None:
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
    Chaos().main()
