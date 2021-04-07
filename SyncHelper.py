# pylint: disable=import-error
from DatabaseHelper import Database
from MonicaHelper import Monica
from GoogleHelper import Google
from logging import Logger
from datetime import datetime

class Sync():
    def __init__(self, log: Logger, monicaHandler: Monica, googleHandler: Google, databaseHandler: Database) -> None:
        self.log = log
        self.monica = monicaHandler
        self.google = googleHandler
        self.database = databaseHandler

    def initialSync(self):
        mapping = []
        for contact in self.google.getContacts():
            mId = self.database.getMonicaId(contact)
            if not mId:
                mId = self.monica.findId(contact)
            if mId:
                mapping.append((mId, contact))
        pass

    def __convertGoogleTimestamp(self, timestamp: str) -> datetime:
        '''Converts Google timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')

    def __convertMonicaTimestamp(self, timestamp: str) -> datetime:
        '''Converts Monica timestamp to a datetime object.'''
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
