from logging import Logger
from os.path import abspath
from typing import Dict, Union

from helpers.Exceptions import ConfigError


class Config:
    """Class for parsing config .env files"""

    def __init__(self, log: Logger, raw_config: Dict[str, Union[str, None]]) -> None:
        self._log = log
        self._values = {key: value or "" for key, value in raw_config.items()}
        try:
            self.TOKEN = self._values["TOKEN"]
            self.BASE_URL = self._values["BASE_URL"]
            if not self.TOKEN or self.TOKEN == "YOUR_TOKEN_HERE":
                msg = "Missing required monica token config value!"
                self._log.error(msg)
                raise ConfigError(msg)
            self.CREATE_REMINDERS = self.__get_boolean("CREATE_REMINDERS")
            self.DELETE_ON_SYNC = self.__get_boolean("DELETE_ON_SYNC")
            self.STREET_REVERSAL = self.__get_boolean("STREET_REVERSAL")
            self.FIELDS = self.__get_array("FIELDS")
            self.GOOGLE_LABELS_INCLUDE = self.__get_array("GOOGLE_LABELS_INCLUDE")
            self.GOOGLE_LABELS_EXCLUDE = self.__get_array("GOOGLE_LABELS_EXCLUDE")
            self.MONICA_LABELS_INCLUDE = self.__get_array("MONICA_LABELS_INCLUDE")
            self.MONICA_LABELS_EXCLUDE = self.__get_array("MONICA_LABELS_EXCLUDE")
            self.DATABASE_FILE = abspath(self._values["DATABASE_FILE"])
            self.GOOGLE_TOKEN_FILE = abspath(self._values["GOOGLE_TOKEN_FILE"])
            self.GOOGLE_CREDENTIALS_FILE = abspath(self._values["GOOGLE_CREDENTIALS_FILE"])
        except Exception as e:
            raise ConfigError("Error parsing config, check syntax and required args!") from e

    def __get_boolean(self, key: str) -> bool:
        """Get a boolean value from config as Python boolean"""
        value_str = self._values[key].lower()
        return value_str in ["true", "1", "t", "y"]

    def __get_array(self, key: str) -> list:
        """Get an array from config as Python list"""
        values_str = self._values.get(key, "")
        if not values_str:
            return []
        return [v.strip() for v in values_str.split(",")]
