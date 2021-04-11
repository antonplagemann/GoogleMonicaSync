import sqlite3
from logging import Logger
from typing import Union
from datetime import datetime


class Database():
    '''Handles all database related stuff.'''

    def __init__(self, log: Logger, filename: str) -> None:
        self.log = log
        # pylint: disable=no-member
        self.connection = sqlite3.connect(filename)
        self.cursor = self.connection.cursor()
        self.__initializeDatabase()

    def deleteAndInitialize(self) -> None:
        '''Deletes all tables from the database and creates new ones.'''
        deleteSyncTableSql = '''
        DROP TABLE IF EXISTS sync;
        '''
        deleteConfigTableSql = '''
        DROP TABLE IF EXISTS config;
        '''
        self.cursor.execute(deleteSyncTableSql)
        self.cursor.execute(deleteConfigTableSql)
        self.connection.commit()
        self.__initializeDatabase()

    def __initializeDatabase(self):
        """Initializes the database with all tables."""
        createSyncTableSql = '''
        CREATE TABLE IF NOT EXISTS sync (
        googleId VARCHAR(50) NOT NULL UNIQUE,
        monicaId VARCHAR(10) NOT NULL UNIQUE,
        googleFullName VARCHAR(50) NULL,
        monicaFullName VARCHAR(50) NULL,
        googleLastChanged DATETIME NULL,
        monicaLastChanged DATETIME NULL);
        '''
        createConfigTableSql = '''
        CREATE TABLE IF NOT EXISTS config (
        googleNextSyncToken VARCHAR(100) NULL UNIQUE,
        tokenLastUpdated DATETIME NULL);
        '''
        self.cursor.execute(createSyncTableSql)
        self.cursor.execute(createConfigTableSql)
        self.connection.commit()

    def insertData(self, googleId: str, monicaId: str, googleFullName: str = 'NULL',
                   monicaFullName: str = 'NULL', googleLastChanged: str = 'NULL',
                   monicaLastChanged: str = 'NULL') -> None:
        '''Inserts the given data into the database. Needs at least a Monica id AND a Google id'''
        insertSql = '''
        INSERT INTO sync(googleId, monicaId, googleFullName, monicaFullName,
                        googleLastChanged, monicaLastChanged)
        VALUES(?,?,?,?,?,?)
        '''
        self.cursor.execute(insertSql, (googleId, str(monicaId), googleFullName, monicaFullName,
                                        googleLastChanged, monicaLastChanged))
        self.connection.commit()

    def update(self, googleId: str = None, monicaId: str = None,
               googleFullName: str = None, monicaFullName: str = None,
               googleLastChanged: str = None, monicaLastChanged: str = None) -> None:
        '''Updates a dataset in the database. Needs at least a Monica id OR a Google id and the related data.'''
        if monicaId:
            if monicaFullName:
                self.__updateFullNameByMonicaId(str(monicaId), monicaFullName)
            if monicaLastChanged:
                self.__updateMonicaLastChanged(
                    str(monicaId), monicaLastChanged)
            else:
                self.log.error("Unknown database update arguments!")
        if googleId:
            if googleFullName:
                self.__updateFullNameByGoogleId(googleId, googleFullName)
            if googleLastChanged:
                self.__updateGoogleLastChanged(googleId, googleLastChanged)
            else:
                self.log.error("Unknown database update arguments!")
        if not monicaId and not googleId:
            self.log.error("Unknown database update arguments!")

    def __updateFullNameByMonicaId(self, monicaId: str, monicaFullName: str) -> None:
        insertSql = "UPDATE sync SET monicaFullName = ? WHERE monicaId = ?"
        self.cursor.execute(insertSql, (monicaFullName, str(monicaId)))
        self.connection.commit()

    def __updateFullNameByGoogleId(self, googleId: str, googleFullName: str) -> None:
        insertSql = "UPDATE sync SET googleFullName = ? WHERE googleId = ?"
        self.cursor.execute(insertSql, (googleFullName, googleId))
        self.connection.commit()

    def __updateMonicaLastChanged(self, monicaId: str, monicaLastChanged: str) -> None:
        insertSql = "UPDATE sync SET monicaLastChanged = ? WHERE monicaId = ?"
        self.cursor.execute(insertSql, (monicaLastChanged, str(monicaId)))
        self.connection.commit()

    def __updateGoogleLastChanged(self, googleId: str, googleLastChanged: str) -> None:
        insertSql = "UPDATE sync SET googleLastChanged = ? WHERE googleId = ?"
        self.cursor.execute(insertSql, (googleLastChanged, googleId))
        self.connection.commit()

    def findById(self, googleId: str = None, monicaId: str = None) -> Union[tuple, None]:
        '''Search for a contact row in the database. Returns None if not found.
           Needs Google id OR Monica id'''
        if monicaId:
            row = self.__findByMonicaId(str(monicaId))
        elif googleId:
            row = self.__findByGoogleId(googleId)
        else:
            self.log.error("Unknown database find arguments!")
        if row:
            gId, mId, googleFullName, monicaFullName, googleLastChanged, monicaLastChanged = row
            return gId, str(mId), googleFullName, monicaFullName, googleLastChanged, monicaLastChanged
        return None

    def getIdMapping(self) -> dict:
        '''Returns a dictionary with the {monicaId:googleId} mapping from the database'''
        findSql = "SELECT googleId,monicaId FROM sync"
        self.cursor.execute(findSql)
        mapping = {googleId: str(monicaId)
                   for googleId, monicaId in self.cursor.fetchall()}
        return mapping

    def __findByMonicaId(self, monicaId: str) -> list:
        findSql = "SELECT * FROM sync WHERE monicaId=?"
        self.cursor.execute(findSql, (str(monicaId),))
        return self.cursor.fetchone()

    def __findByGoogleId(self, googleId: str) -> list:
        findSql = "SELECT * FROM sync WHERE googleId=?"
        self.cursor.execute(findSql, (googleId,))
        return self.cursor.fetchone()

    def delete(self, googleId: str, monicaId: str) -> None:
        '''Deletes a row from the database. Needs Monica id AND Google id.'''
        deleteSql = "DELETE FROM sync WHERE monicaId=? AND googleId=?"
        self.cursor.execute(deleteSql, (str(monicaId), googleId))
        self.connection.commit()

    def getGoogleNextSyncToken(self) -> Union[str, None]:
        '''Returns the next sync token.'''
        findSql = "SELECT * FROM config WHERE ROWID=1"
        self.cursor.execute(findSql)
        row = self.cursor.fetchone()
        if row:
            return row[0]
        return None

    def updateGoogleNextSyncToken(self, token: str) -> None:
        '''Updates the given token in the database.'''
        timestamp = datetime.now().strftime('%F %H:%M:%S')
        deleteSql = "DELETE FROM config WHERE ROWID=1"
        insertSql = "INSERT INTO config(googleNextSyncToken, tokenLastUpdated) VALUES(?,?)"
        self.cursor.execute(deleteSql)
        self.cursor.execute(insertSql, (token, timestamp))
        self.connection.commit()
