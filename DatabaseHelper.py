from os.path import exists
import sqlite3
from logging import Logger

class Database():
    def __init__(self, log: Logger, filename: str) -> None:
        self.log = log
        oldFile = exists(filename)
        # pylint: disable=no-member
        self.connection = sqlite3.connect(filename)
        self.cursor = self.connection.cursor()
        if not oldFile:
            self.__initializeDatabase()
    
    def __initializeDatabase(self):
        """Initializes the database."""
        pass

    def getMonicaId(self, id: str):
        '''Search for a Monica contact id in the database. Returns none if not found.'''
        return None
