import argparse
import logging
import os
import sys
from os.path import abspath, join

from dotenv import dotenv_values, find_dotenv

from helpers.ConfigHelper import Config
from helpers.DatabaseHelper import Database
from helpers.Exceptions import ConfigError
from helpers.GoogleHelper import Google
from helpers.MonicaHelper import Monica
from helpers.SyncHelper import Sync

VERSION = "v4.0.0"
LOG_FOLDER = "logs"
LOG_FILENAME = "sync.log"
DEFAULT_CONFIG_FILEPATH = join("helpers", ".env.default")
# Google -> Monica contact syncing script
# Make sure you installed all requirements using 'pip install -r requirements.txt'


def main() -> None:
    try:
        # Setup argument parser
        parser = argparse.ArgumentParser(description='Syncs Google contacts to a Monica instance.')
        parser.add_argument('-i', '--initial', action='store_true',
                            required=False, help="build the syncing database and do a full sync")
        parser.add_argument('-sb', '--syncback', action='store_true',
                            required=False, help="sync new Monica contacts back to Google. "
                                                 "Can be combined with other arguments")
        parser.add_argument('-d', '--delta', action='store_true',
                            required=False,
                            help="do a delta sync of new or changed Google contacts")
        parser.add_argument('-f', '--full', action='store_true',
                            required=False,
                            help="do a full sync and request a new delta sync token")
        parser.add_argument('-c', '--check', action='store_true',
                            required=False,
                            help="check database consistency and report all errors. "
                            "Can be combined with other arguments")
        parser.add_argument('-e', '--env-file', type=str, required=False,
                            help="custom path to your .env config file")

        # Parse arguments
        args = parser.parse_args()

        # Set logging configuration
        log = logging.getLogger("GMSync")
        dotenv_log = logging.getLogger("dotenv.main")
        log.setLevel(logging.INFO)
        logging_format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        log_filename = join(LOG_FOLDER, LOG_FILENAME)
        handler = logging.FileHandler(filename=log_filename, mode='a', encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging_format)
        log.addHandler(handler)
        dotenv_log.addHandler(handler)
        log.info(f"Script started ({VERSION})")

        # Load raw config
        default_config = find_dotenv(DEFAULT_CONFIG_FILEPATH, raise_error_if_not_found=True)
        if args.env_file:
            if not os.path.exists(args.env_file):
                raise ConfigError("Could not find the custom config file, check your input!")
            # Use config from custom path
            user_config = abspath(args.env_file)
        else:
            # Search config path
            user_config = find_dotenv()
        if user_config:
            # Load user config from file
            log.info(f"Loading user config from {user_config}")
            user_config_values = dotenv_values(user_config)
        else:
            # Load user config from environment vars
            log.info("Loading user config from os environment")
            user_config_values = dict(os.environ)
        log.info(f"Loading default config from {default_config}")
        default_config_values = dotenv_values(default_config)
        raw_config = {
            **default_config_values,
            **user_config_values
        }
        log.info("Config loading complete")

        # Parse config
        conf = Config(log, raw_config)
        log.info("Config successfully parsed")

        # Create sync object
        database = Database(log, abspath(conf.DATABASE_FILE))
        google = Google(log, database, abspath(conf.GOOGLE_CREDENTIALS_FILE),
                        abspath(conf.GOOGLE_TOKEN_FILE),
                        conf.GOOGLE_LABELS_INCLUDE, conf.GOOGLE_LABELS_EXCLUDE)
        monica = Monica(log, database, conf.TOKEN, conf.BASE_URL, conf.CREATE_REMINDERS,
                        conf.MONICA_LABELS_INCLUDE, conf.MONICA_LABELS_EXCLUDE)
        sync = Sync(log, database, monica, google, args.syncback, args.check,
                    conf.DELETE_ON_SYNC, conf.STREET_REVERSAL, conf.FIELDS)

        # Print chosen sync arguments (optional ones first)
        print("\nYour choice (unordered):")
        if args.syncback:
            print("- sync back")
        if args.check:
            print("- database check")

        # Start
        if args.initial:
            # Start initial sync
            print("- initial sync\n")
            sync.start_sync('initial')
        elif args.delta:
            # Start initial sync
            print("- delta sync\n")
            sync.start_sync('delta')
        elif args.full:
            # Start initial sync
            print("- full sync\n")
            sync.start_sync('full')
        elif args.syncback:
            # Start sync back from Monica to Google
            print("")
            sync.start_sync('syncBack')
        elif args.check:
            # Start database error check
            print("")
            sync.check_database()
        else:
            # Wrong arguments
            print("Unknown sync arguments, check your input!\n")
            parser.print_help()
            sys.exit(2)

        # Its over now
        log.info("Script ended\n")

    except Exception as e:
        log.exception(e)
        log.info("Script aborted")
        print(f"\nScript aborted: {type(e).__name__}: {str(e)}")
        print(f"See log file ({log_filename}) for all details")
        raise SystemExit(1) from e


if __name__ == '__main__':
    main()
