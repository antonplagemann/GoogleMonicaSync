VERSION = "v0.1"
# Google-Monica-Sync
# Make sure you installed all requirements using 'pip install -r requirements.txt'
# pylint: disable=import-error
import logging
from conf import TOKEN, BASE_URL, CREATE_REMINDERS, SYNC_BACK, DELETE_ON_SYNC
from DatabaseHelper import Database
from MonicaHelper import Monica
from GoogleHelper import Google
from SyncHelper import Sync

# Get module specific logger
log = logging.getLogger('GMSync')

def getTestingData(filename: str) -> list:
    '''Returns sample data saved as json file. Only for developing purposes to avoid api penetration.'''
    import json
    with open(filename) as handle:
        data = json.load(handle)
    return data

def updateTestingData(filename: str, contactList: list) -> None:
    '''Creates sample data saved as json file. Only for developing purposes to avoid api penetration.'''
    import json
    with open(filename, 'w') as handle:
        json.dump(contactList, handle, indent=4)

def main() -> None:
    #try:
    # Logging configuration
    log.setLevel(logging.INFO)
    format = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler = logging.FileHandler(filename='Sync.log', mode='a', encoding="utf8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(format)
    log.addHandler(handler)
    log.info(f"Sync started")

    # More code
    database = Database(log, 'syncState.db')
    google = Google(log, database)#, getTestingData('GoogleSampleData.json'))
    monica = Monica(log, TOKEN, BASE_URL, CREATE_REMINDERS, database)#, getTestingData('MonicaSampleData.json'))
    
    # Update testing data
    #monica = Monica(log, TOKEN, BASE_URL, CREATE_REMINDERS, database)
    #google = Google(log, database)
    #updateTestingData('MonicaSampleData.json', monica.getContacts())
    #updateTestingData('GoogleSampleData.json', google.getContacts())

    sync = Sync(log, monica, google, database, SYNC_BACK, DELETE_ON_SYNC)

    print("")

    sync.startSync()

    log.info("Sync ended\n")
    '''
    except Exception as e:
        log.error(str(e))
        print(str(e))
        log.info("Sync ended\n")
        sys.exit(1)
    '''

if __name__ == '__main__':
    main()