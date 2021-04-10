# pylint: disable=import-error
import logging
from conf import TOKEN, BASE_URL, CREATE_REMINDERS, SYNC_BACK, DELETE_ON_SYNC
from DatabaseHelper import Database
from MonicaHelper import Monica
from GoogleHelper import Google
from SyncHelper import Sync
import sys
import argparse
VERSION = "v1.1"
# Google -> Monica syncing script
# Make sure you installed all requirements using 'pip install -r requirements.txt'


# Get module specific logger
log = logging.getLogger('GMSync')


def getTestingData(filename: str) -> list:
    '''Returns sample data saved as json file. Only for developing purposes to avoid intensive api penetration.'''
    import json
    with open(filename) as handle:
        data = json.load(handle)
    return data


def updateTestingData(filename: str, contactList: list) -> None:
    '''Creates sample data saved as json file. Only for developing purposes to avoid intensive api penetration.'''
    import json
    with open(filename, 'w') as handle:
        json.dump(contactList, handle, indent=4)


def fetchAndSaveTestingData() -> None:
    '''Fetches new data from Monica and Google and saves it to a json file. Only for developing purposes.'''
    database = Database(log, 'syncState.db')
    monica = Monica(log, TOKEN, BASE_URL, CREATE_REMINDERS, database)
    google = Google(log, database)
    updateTestingData('MonicaSampleData.json', monica.getContacts())
    updateTestingData('GoogleSampleData.json', google.getContacts())


def runWithTestingData() -> None:
    '''Does a script run without fetching full data to avoid intensive api penetration.'''
    database = Database(log, 'syncState.db')
    google = Google(log, database, getTestingData('GoogleSampleData.json'))
    monica = Monica(log, TOKEN, BASE_URL, CREATE_REMINDERS, database, getTestingData('MonicaSampleData.json'))
    sync = Sync(log, monica, google, database, SYNC_BACK, DELETE_ON_SYNC)
    print("")
    sync.startSync()
    raise Exception("Test sync ended")


def main() -> None:
    try:
        # Setup argument parser
        parser = argparse.ArgumentParser(description='Syncs Google contacts to a Monica instance.')
        parser.add_argument('-i', '--initial', action='store_true',
                            required=False, help="Do a initial sync and rebuild the database")
        parser.add_argument('-c', '--check', action='store_true',
                            required=False, help="Not implemented yet")

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
        google = Google(log, database)
        monica = Monica(log, TOKEN, BASE_URL, CREATE_REMINDERS, database)
        sync = Sync(log, monica, google, database, SYNC_BACK, DELETE_ON_SYNC)

        # A newline makes things more beatiful
        print("")

        if args.initial:
            # Start initial sync
            sync.startSync('initial')
        else:
            # Start delta or full sync
            sync.startSync()

        # Its over now
        log.info("Sync ended\n")

    except Exception as e:
        log.error(str(e))
        print(str(e))
        log.info("Sync aborted\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
