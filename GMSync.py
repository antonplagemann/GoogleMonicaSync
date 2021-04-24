# pylint: disable=import-error
import logging
from conf import TOKEN, BASE_URL, CREATE_REMINDERS, DELETE_ON_SYNC, \
                 STREET_REVERSAL, GOOGLE_LABELS, MONICA_LABELS, FIELDS
from DatabaseHelper import Database
from MonicaHelper import Monica
from GoogleHelper import Google
from SyncHelper import Sync
import sys
import argparse
VERSION = "v2.2.2"
# Google -> Monica contact syncing script
# Make sure you installed all requirements using 'pip install -r requirements.txt'


# Get module specific logger
log = logging.getLogger('GMSync')


def getTestingData(filename: str) -> list:
    '''Only for developing purposes. Returns sample data from a json file to avoid intensive api penetration.'''
    import json
    with open(filename) as handle:
        data = json.load(handle)
    return data


def updateTestingData(filename: str, contactList: list) -> None:
    '''Only for developing purposes. Creates sample data saved as json file to avoid intensive api penetration.'''
    import json
    with open(filename, 'w') as handle:
        json.dump(contactList, handle, indent=4)


def fetchAndSaveTestingData() -> None:
    '''Only for developing purposes. Fetches new data from Monica and Google and saves it to a json file.'''
    database = Database(log, 'syncState.db')
    monica = Monica(log, database, TOKEN, BASE_URL, CREATE_REMINDERS, MONICA_LABELS)
    google = Google(log, database, GOOGLE_LABELS)
    updateTestingData('MonicaSampleData.json', monica.getContacts())
    updateTestingData('GoogleSampleData.json', google.getContacts())


def main() -> None:
    try:
        # Setup argument parser
        parser = argparse.ArgumentParser(description='Syncs Google contacts to a Monica instance.')
        parser.add_argument('-i', '--initial', action='store_true',
                            required=False, help="build the syncing database and do a full sync")
        parser.add_argument('-sb', '--syncback', action='store_true',
                            required=False, help="sync new Monica contacts back to Google. Can be combined with other arguments")
        parser.add_argument('-d', '--delta', action='store_true',
                            required=False, help="do a delta sync of new or changed Google contacts")
        parser.add_argument('-f', '--full', action='store_true',
                            required=False, help="do a full sync and request a new delta sync token")
        #parser.add_argument('-c', '--check', action='store_true',
        #                    required=False, help="not implemented yet")

        # Parse arguments
        args = parser.parse_args()

        # Logging configuration
        log.setLevel(logging.INFO)
        format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler = logging.FileHandler(filename='Sync.log', mode='a', encoding="utf8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(format)
        log.addHandler(handler)
        log.info(f"Sync started ({VERSION})")

        # Create sync object
        database = Database(log, 'syncState.db')
        google = Google(log, database, GOOGLE_LABELS)
        monica = Monica(log, database, TOKEN, BASE_URL, CREATE_REMINDERS, MONICA_LABELS)
        sync = Sync(log, database, monica, google, args.syncback, DELETE_ON_SYNC, STREET_REVERSAL, FIELDS)

        # A newline makes things more beautiful
        print("")

        if args.initial:
            # Start initial sync
            sync.startSync('initial')
        elif args.delta:
            # Start initial sync
            sync.startSync('delta')
        elif args.full:
            # Start initial sync
            sync.startSync('full')
        elif args.syncback:
            # Start sync back from Monica to Google
            sync.startSync('syncBack')
        else:
            # Wrong arguments
            print("Unknown sync arguments, check your input!\n")
            parser.print_help()
            sys.exit(2)

        # Its over now
        log.info("Sync ended\n")

    except Exception as e:
        msg = f"Sync aborted: {str(e)}\n"
        log.error(msg)
        print("\n" + msg)
        sys.exit(1)


if __name__ == '__main__':
    main()
