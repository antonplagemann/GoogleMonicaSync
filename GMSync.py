import argparse
import logging
import sys

try:
    from conf import (BASE_URL, CREATE_REMINDERS, DELETE_ON_SYNC, FIELDS,
                      GOOGLE_LABELS, MONICA_LABELS, STREET_REVERSAL, TOKEN)
except ImportError:
    print("\nFailed to import config settings!\n"
          "Please verify that you have the latest version of the conf.py file "
          "available on GitHub and check for possible typos!")
    sys.exit(1)

from DatabaseHelper import Database
from GoogleHelper import Google
from MonicaHelper import Monica
from SyncHelper import Sync

VERSION = "v3.2.1"
DATABASE_FILENAME = "syncState.db"
LOG_FILENAME = 'Sync.log'
# Google -> Monica contact syncing script
# Make sure you installed all requirements using 'pip install -r requirements.txt'

# Get module specific logger
log = logging.getLogger('GMSync')


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

        # Parse arguments
        args = parser.parse_args()

        # Logging configuration
        log.setLevel(logging.INFO)
        logging_format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler = logging.FileHandler(filename=LOG_FILENAME, mode='a', encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging_format)
        log.addHandler(handler)
        log.info(f"Script started ({VERSION})")

        # Create sync object
        database = Database(log, DATABASE_FILENAME)
        google = Google(log, database, GOOGLE_LABELS)
        monica = Monica(log, database, TOKEN, BASE_URL, CREATE_REMINDERS, MONICA_LABELS)
        sync = Sync(log, database, monica, google, args.syncback, args.check,
                    DELETE_ON_SYNC, STREET_REVERSAL, FIELDS)

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
        msg = f"Script aborted: {type(e).__name__}: {str(e)}\n"
        log.exception(e)
        print("\n" + msg)
        raise SystemExit(1) from e


if __name__ == '__main__':
    main()
