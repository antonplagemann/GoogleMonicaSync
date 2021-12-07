import sqlite3
from datetime import datetime
from logging import Logger
from typing import Tuple, Union, List


class DatabaseEntry():
    '''Creates a database row object for inserting into the database. 
    Needs at least a Monica id AND a Google id.'''

    def __init__(self, google_id: str, monica_id: str, google_full_name: str = 'NULL',
                   monica_full_name: str = 'NULL', google_last_changed: str = 'NULL',
                   monica_last_changed: str = 'NULL') -> None:
        insert_sql = '''
        INSERT INTO sync(googleId, monicaId, googleFullName, monicaFullName,
                        googleLastChanged, monicaLastChanged)
        VALUES(?,?,?,?,?,?)
        '''
        self.insert_statement = insert_sql, (google_id, str(monica_id), 
                                google_full_name, monica_full_name,
                                google_last_changed, monica_last_changed)

    def get_insert_statement(self) -> Tuple[str, tuple]:
        return self.insert_statement

class Database():
    '''Handles all database related stuff.'''

    def __init__(self, log: Logger, filename: str) -> None:
        self.log = log
        # pylint: disable=no-member
        self.connection = sqlite3.connect(filename)
        self.cursor = self.connection.cursor()
        self.__initialize_database()

    def delete_and_initialize(self) -> None:
        '''Deletes all tables from the database and creates new ones.'''
        delete_sync_table_sql = '''
        DROP TABLE IF EXISTS sync;
        '''
        delete_config_table_sql = '''
        DROP TABLE IF EXISTS config;
        '''
        self.cursor.execute(delete_sync_table_sql)
        self.cursor.execute(delete_config_table_sql)
        self.connection.commit()
        self.__initialize_database()

    def __initialize_database(self):
        """Initializes the database with all tables."""
        create_sync_table_sql = '''
        CREATE TABLE IF NOT EXISTS sync (
        googleId VARCHAR(50) NOT NULL UNIQUE,
        monicaId VARCHAR(10) NOT NULL UNIQUE,
        googleFullName VARCHAR(50) NULL,
        monicaFullName VARCHAR(50) NULL,
        googleLastChanged DATETIME NULL,
        monicaLastChanged DATETIME NULL);
        '''
        create_config_table_sql = '''
        CREATE TABLE IF NOT EXISTS config (
        googleNextSyncToken VARCHAR(100) NULL UNIQUE,
        tokenLastUpdated DATETIME NULL);
        '''
        self.cursor.execute(create_sync_table_sql)
        self.cursor.execute(create_config_table_sql)
        self.connection.commit()

    def insert_data(self, database_entry: DatabaseEntry) -> None:
        '''Inserts the given data into the database.'''
        self.cursor.execute(*database_entry.get_insert_statement())
        self.connection.commit()

    def update(self, google_id: str = None, monica_id: str = None,
               google_full_name: str = None, monica_full_name: str = None,
               google_last_changed: str = None, monica_last_changed: str = None) -> None:
        '''Updates a dataset in the database. Needs at least a Monica id OR a Google id and the related data.'''
        UNKNOWN_ARGUMENTS = "Unknown database update arguments!"
        if monica_id:
            if monica_full_name:
                self.__update_full_name_by_monica_id(str(monica_id), monica_full_name)
            if monica_last_changed:
                self.__update_monica_last_changed(str(monica_id), monica_last_changed)
            else:
                self.log.error(UNKNOWN_ARGUMENTS)
        if google_id:
            if google_full_name:
                self.__update_full_name_by_google_id(google_id, google_full_name)
            if google_last_changed:
                self.__update_google_last_changed(google_id, google_last_changed)
            else:
                self.log.error(UNKNOWN_ARGUMENTS)
        if not monica_id and not google_id:
            self.log.error(UNKNOWN_ARGUMENTS)

    def __update_full_name_by_monica_id(self, monica_id: str, monica_full_name: str) -> None:
        insert_sql = "UPDATE sync SET monicaFullName = ? WHERE monicaId = ?"
        self.cursor.execute(insert_sql, (monica_full_name, str(monica_id)))
        self.connection.commit()

    def __update_full_name_by_google_id(self, google_id: str, google_full_name: str) -> None:
        insert_sql = "UPDATE sync SET googleFullName = ? WHERE googleId = ?"
        self.cursor.execute(insert_sql, (google_full_name, google_id))
        self.connection.commit()

    def __update_monica_last_changed(self, monica_id: str, monica_last_changed: str) -> None:
        insert_sql = "UPDATE sync SET monicaLastChanged = ? WHERE monicaId = ?"
        self.cursor.execute(insert_sql, (monica_last_changed, str(monica_id)))
        self.connection.commit()

    def __update_google_last_changed(self, google_id: str, google_last_changed: str) -> None:
        insert_sql = "UPDATE sync SET googleLastChanged = ? WHERE googleId = ?"
        self.cursor.execute(insert_sql, (google_last_changed, google_id))
        self.connection.commit()

    def find_by_id(self, google_id: str = None, monica_id: str = None) -> Union[tuple, None]:
        '''Search for a contact row in the database. Returns None if not found.
           Needs Google id OR Monica id'''
        if monica_id:
            row = self.__find_by_monica_id(str(monica_id))
        elif google_id:
            row = self.__find_by_google_id(google_id)
        else:
            self.log.error("Unknown database find arguments!")
        if row:
            g_id, m_id, g_full_name, m_full_name, g_last_changed, m_last_changed = row
            return g_id, str(m_id), g_full_name, m_full_name, g_last_changed, m_last_changed
        return None

    def get_id_mapping(self) -> dict:
        '''Returns a dictionary with the {monicaId:googleId} mapping from the database'''
        find_sql = "SELECT googleId,monicaId FROM sync"
        self.cursor.execute(find_sql)
        mapping = {google_id: str(monica_id)
                   for google_id, monica_id in self.cursor.fetchall()}
        return mapping

    def __find_by_monica_id(self, monica_id: str) -> List[tuple]:
        find_sql = "SELECT * FROM sync WHERE monicaId=?"
        self.cursor.execute(find_sql, (str(monica_id),))
        return self.cursor.fetchone()

    def __find_by_google_id(self, google_id: str) -> List[tuple]:
        find_sql = "SELECT * FROM sync WHERE googleId=?"
        self.cursor.execute(find_sql, (google_id,))
        return self.cursor.fetchone()

    def delete(self, google_id: str, monica_id: str) -> None:
        '''Deletes a row from the database. Needs Monica id AND Google id.'''
        delete_sql = "DELETE FROM sync WHERE monicaId=? AND googleId=?"
        self.cursor.execute(delete_sql, (str(monica_id), google_id))
        self.connection.commit()

    def get_google_next_sync_token(self) -> Union[str, None]:
        '''Returns the next sync token.'''
        find_sql = "SELECT * FROM config WHERE ROWID=1"
        self.cursor.execute(find_sql)
        row = self.cursor.fetchone()
        if row:
            return row[0]
        return None

    def update_google_next_sync_token(self, token: str) -> None:
        '''Updates the given token in the database.'''
        timestamp = datetime.now().strftime('%F %H:%M:%S')
        delete_sql = "DELETE FROM config WHERE ROWID=1"
        insert_sql = "INSERT INTO config(googleNextSyncToken, tokenLastUpdated) VALUES(?,?)"
        self.cursor.execute(delete_sql)
        self.cursor.execute(insert_sql, (token, timestamp))
        self.connection.commit()
