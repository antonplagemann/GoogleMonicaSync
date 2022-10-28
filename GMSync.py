import argparse
import logging
import logging.handlers
import os
import sys
from os.path import abspath, join
from typing import Tuple, Union

from dotenv import dotenv_values, find_dotenv  # type: ignore
from dotenv.main import set_key  # type: ignore

from helpers.ConfigHelper import Config
from helpers.DatabaseHelper import Database
from helpers.Exceptions import ConfigError
from helpers.GoogleHelper import Google
from helpers.MonicaHelper import Monica
from helpers.SyncHelper import Sync

VERSION = "v5.0.0"
LOG_FOLDER = "logs"
LOG_FILENAME = "sync.log"
DEFAULT_CONFIG_FILEPATH = join("helpers", ".env.default")
# Google -> Monica contact syncing script
# Make sure you installed all requirements using 'pip install -r requirements.txt'


class GMSync:
    def main(self) -> None:
        try:
            # Create logger
            self.create_logger()
            self.log.info(f"Script started ({VERSION})")

            # Create argument parser
            self.create_argument_parser()

            # Convert environment if requested (-u)
            if self.args.update:
                self.update_environment()

            # Load config
            self.load_config()

            # Create syslog handler
            if self.conf.SYSLOG_TARGET:
                address: Union[Tuple[str, int], str] = (
                    (self.conf.SYSLOG_TARGET, int(self.conf.SYSLOG_PORT))
                    if self.conf.SYSLOG_PORT
                    else self.conf.SYSLOG_TARGET
                )
                syslog_handler = logging.handlers.SysLogHandler(address=address)
                syslog_handler.setFormatter(self.logging_format)
                self.log.addHandler(syslog_handler)

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

            # It's over now
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
        log = logging.getLogger("GMSync")
        dotenv_log = logging.getLogger("dotenv.main")
        log.setLevel(logging.INFO)
        self.logging_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        log_filepath = join(LOG_FOLDER, LOG_FILENAME)
        handler = logging.FileHandler(filename=log_filepath, mode="a", encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(self.logging_format)
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
            help="build the syncing database and do a full sync",
        )
        parser.add_argument(
            "-d",
            "--delta",
            action="store_true",
            required=False,
            help="do a delta sync of new or changed Google contacts",
        )
        parser.add_argument(
            "-f",
            "--full",
            action="store_true",
            required=False,
            help="do a full sync and request a new delta sync token",
        )
        parser.add_argument(
            "-sb",
            "--syncback",
            action="store_true",
            required=False,
            help="sync new Monica contacts back to Google. Can be combined with other arguments",
        )
        parser.add_argument(
            "-c",
            "--check",
            action="store_true",
            required=False,
            help="check database consistency and report all errors. "
            "Can be combined with other arguments",
        )
        parser.add_argument(
            "-e", "--env-file", type=str, required=False, help="custom path to your .env config file"
        )
        parser.add_argument(
            "-u",
            "--update",
            action="store_true",
            required=False,
            help="Updates the environment files from 3.x to v4.x scheme",
        )

        # Parse arguments
        self.parser = parser
        self.args = parser.parse_args()

    def load_config(self) -> None:
        """Loads the config from file or environment variables"""
        # Load default config
        self.log.info("Loading config (last value wins)")
        default_config = find_dotenv(DEFAULT_CONFIG_FILEPATH, raise_error_if_not_found=True)
        self.log.info(f"Loading default config from {default_config}")
        default_config_values = dotenv_values(default_config)
        if self.args.env_file:
            if not os.path.exists(self.args.env_file):
                raise ConfigError("Could not find the custom user config file, check your input!")
            # Load config from custom path
            user_config = abspath(self.args.env_file)
        else:
            # Search config path
            user_config = find_dotenv()
        if user_config:
            # Load config from file
            self.log.info(f"Loading file config from {user_config}")
            file_config_values = dotenv_values(user_config)
        else:
            file_config_values = {}

        # Load config from environment vars
        self.log.info("Loading os environment config")
        environment_config_values = dict(os.environ)
        self.log.info("Config loading complete")
        raw_config = {**default_config_values, **file_config_values, **environment_config_values}

        # Parse config
        self.conf = Config(self.log, raw_config)
        self.log.info("Config successfully parsed")

    def create_sync_helper(self) -> None:
        """Creates the main sync class object"""
        # Create sync objects
        database = Database(self.log, self.conf.DATABASE_FILE)
        google = Google(
            self.log,
            database,
            self.conf.GOOGLE_CREDENTIALS_FILE,
            self.conf.GOOGLE_TOKEN_FILE,
            self.conf.GOOGLE_LABELS_INCLUDE,
            self.conf.GOOGLE_LABELS_EXCLUDE,
            self.args.initial,
        )
        monica = Monica(
            self.log,
            database,
            self.conf.TOKEN,
            self.conf.BASE_URL,
            self.conf.CREATE_REMINDERS,
            self.conf.MONICA_LABELS_INCLUDE,
            self.conf.MONICA_LABELS_EXCLUDE,
        )
        self.sync = Sync(
            self.log,
            database,
            monica,
            google,
            self.args.syncback,
            self.args.check,
            self.conf.DELETE_ON_SYNC,
            self.conf.STREET_REVERSAL,
            self.conf.FIELDS,
        )

    def update_environment(self):
        """Updates the config and other environment files to work with v4.x.x"""
        self.log.info("Start updating environment")

        # Make 'data' folder
        if not os.path.exists("data"):
            os.makedirs("data")
            msg = "'data' folder created"
            self.log.info(msg)
            print(msg)

        # Convert config to '.env' file
        env_file = ".env"
        open(env_file, "w").close()
        from conf import (  # type: ignore
            BASE_URL,
            CREATE_REMINDERS,
            DELETE_ON_SYNC,
            FIELDS,
            GOOGLE_LABELS,
            MONICA_LABELS,
            STREET_REVERSAL,
            TOKEN,
        )

        set_key(env_file, "TOKEN", TOKEN)
        set_key(env_file, "BASE_URL", BASE_URL)
        set_key(env_file, "CREATE_REMINDERS", str(CREATE_REMINDERS))
        set_key(env_file, "DELETE_ON_SYNC", str(DELETE_ON_SYNC))
        set_key(env_file, "STREET_REVERSAL", str(STREET_REVERSAL))
        set_key(env_file, "FIELDS", ",".join([field for field, is_true in FIELDS.items() if is_true]))
        set_key(env_file, "GOOGLE_LABELS_INCLUDE", ",".join(GOOGLE_LABELS["include"]))
        set_key(env_file, "GOOGLE_LABELS_EXCLUDE", ",".join(GOOGLE_LABELS["exclude"]))
        set_key(env_file, "MONICA_LABELS_INCLUDE", ",".join(MONICA_LABELS["include"]))
        set_key(env_file, "MONICA_LABELS_EXCLUDE", ",".join(MONICA_LABELS["exclude"]))
        msg = "'.env' file created, old 'conf.py' can be deleted now"
        self.log.info(msg)
        print(msg)

        # Move token, credentials and database inside new 'data' folder
        files = ["syncState.db", "token.pickle", "credentials.json"]
        for filename in files:
            try:
                os.rename(filename, f"data/{filename}")
                msg = f"'{filename}' moved to 'data/{filename}'"
                self.log.info(msg)
                print(msg)
            except FileNotFoundError:
                msg = f"Could not move {filename}, file not found!"
                print(msg)
                self.log.warning(msg)

        # Finished
        self.log.info("Finished updating environment")


if __name__ == "__main__":
    GMSync().main()
