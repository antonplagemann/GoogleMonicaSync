import sqlite3
from logging import Logger
from typing import Union, Tuple

class Database():
    def __init__(self, log: Logger, filename: str) -> None:
        self.log = log
        # pylint: disable=no-member
        self.connection = sqlite3.connect(filename)
        self.cursor = self.connection.cursor()
        self.__initializeDatabase()
    
    def __initializeDatabase(self):
        """Initializes the database with all tables."""
        newSyncTableSql = '''
        CREATE TABLE IF NOT EXISTS sync (
        monicaId VARCHAR(10) NOT NULL,
        googleId VARCHAR(10) NOT NULL,
        fullName VARCHAR(50) NULL,
        monicaLastChanged DATETIME NULL,
        googleLastChanged DATETIME NULL,
        UNIQUE(monicaId,googleId));
        '''
        newConfigTableSql = '''
        CREATE TABLE IF NOT EXISTS config (
        googleNextSyncToken VARCHAR(100) NULL,
        UNIQUE(googleNextSyncToken));
        '''
        newGoogleNextSyncTokenRow = "INSERT INTO config(googleNextSyncToken) VALUES(NULL)"
        self.cursor.execute(newSyncTableSql)
        self.cursor.execute(newConfigTableSql)
        self.cursor.execute(newGoogleNextSyncTokenRow)
        self.connection.commit()
    
    def insertData(self, monicaId: str, googleId: str, fullName: str = 'NULL', 
                monicaLastChanged: str = 'NULL', googleLastChanged: str = 'NULL') -> None:
        insertSql = '''
        INSERT INTO sync(monicaId,googleId,fullName,monicaLastChanged,
                        googleLastChanged)
        VALUES(?,?,?,?,?)
        '''
        self.cursor.execute(insertSql,(monicaId, googleId, fullName, monicaLastChanged, 
                            googleLastChanged))
        self.connection.commit()

    def update(self, monicaId: str = None, googleId: str = None, fullName: str = None, 
                monicaLastChanged: str = None, googleLastChanged: str = None) -> None:
        '''Updates a dataset in the database. Needs positional arguments!'''
        if monicaId:
            if fullName:
                self.__updateFullNameByMonicaId(monicaId, fullName)
            elif monicaLastChanged:
                self.__updateMonicaLastChanged(monicaId, monicaLastChanged)
            else:
                self.log.error("Unknown database update arguments!")
        elif googleId:
            if fullName:
                self.__updateFullNameByGoogleId(googleId, fullName)
            elif googleLastChanged:
                self.__updateGoogleLastChanged(googleId, googleLastChanged)
            else:
                self.log.error("Unknown database update arguments!")
        else:
            self.log.error("Unknown database update arguments!")

    def __updateFullNameByMonicaId(self, monicaId: str, fullName: str) -> None:
        insertSql = "UPDATE sync SET fullName = ? WHERE monicaId = ?"
        self.cursor.execute(insertSql,(fullName, monicaId))
        self.connection.commit()

    def __updateFullNameByGoogleId(self, googleId: str, fullName: str) -> None:
        insertSql = "UPDATE sync SET fullName = ? WHERE googleId = ?"
        self.cursor.execute(insertSql,(fullName, googleId))
        self.connection.commit()

    def __updateMonicaLastChanged(self, monicaId: str, monicaLastChanged: str) -> None:
        insertSql = "UPDATE sync SET monicaLastChanged = ? WHERE monicaId = ?"
        self.cursor.execute(insertSql,(monicaLastChanged, monicaId))
        self.connection.commit()

    def __updateGoogleLastChanged(self, googleId: str, googleLastChanged: str) -> None:
        insertSql = "UPDATE sync SET googleLastChanged = ? WHERE googleId = ?"
        self.cursor.execute(insertSql,(googleLastChanged, googleId))
        self.connection.commit()


    def findById(self, monicaId: str = None, googleId: str = None) -> Union[tuple,None]:
        '''Search for a contact id in the database. Returns None if not found.
           Needs positional arguments!'''
        if monicaId:
            row = self.__findByMonicaId(monicaId)
        elif googleId:
            row = self.__findByGoogleId(googleId)
        else:
            self.log.error("Unknown database find arguments!")
        if row:
            return row
        return None

    def __findByMonicaId(self, monicaId: str) -> list:
        findSql = "SELECT * FROM sync WHERE monicaId=?"
        self.cursor.execute(findSql,(monicaId,))
        return self.cursor.fetchone()

    def __findByGoogleId(self, googleId: str) -> list:
        findSql = "SELECT * FROM sync WHERE googleId=?"
        self.cursor.execute(findSql,(googleId,))
        return self.cursor.fetchone()

    def delete(self, monicaId: str, googleId: str) -> None:
        deleteSql = "DELETE FROM sync WHERE monicaId=? AND googleId=?"
        self.cursor.execute(deleteSql,(monicaId, googleId))
        self.connection.commit()

    def getGoogleNextSyncToken(self) -> Union[str,None]:
        findSql = "SELECT * FROM config WHERE ROWID=1"
        self.cursor.execute(findSql)
        row = self.cursor.fetchone()
        if row:
            return row[0]
        return None

    def updateGoogleNextSyncToken(self, token: str) -> None:
        updateSql = "UPDATE config SET googleNextSyncToken = ? WHERE ROWID = 1"
        self.cursor.execute(updateSql,(token,))
        self.connection.commit()
