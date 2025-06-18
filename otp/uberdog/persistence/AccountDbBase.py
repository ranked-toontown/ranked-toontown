# --- ACCOUNT DATABASES ---
# These classes make up the available account database interfaces for Toontown Online.
# At the moment, we have two functional account database interfaces: DeveloperAccountDB, and LocalAccountDB.
# These will be explained further in their respective class definition.
from abc import ABC, abstractmethod

from direct.directnotify import DirectNotifyGlobal


class AccountDbBase(ABC):
    """
    AccountDB is the base class for all account database interface implementations. Inherit from this class when
    creating new account database interfaces, but DO NOT try to use this class on its own; you'll have a bad time!
    """
    notify = DirectNotifyGlobal.directNotify.newCategory('AccountDB')

    def __init__(self, gameServicesManager):
        self.gameServicesManager = gameServicesManager

    @abstractmethod
    def lookup(self, playToken, callback):
        raise NotImplementedError('lookup')  # Must be overridden by subclass.

    @abstractmethod
    def storeAccountID(self, databaseId, accountId, callback):
        raise NotImplementedError('storeAccountID')
