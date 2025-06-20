from typing import Any, Mapping

from direct.directnotify import DirectNotifyGlobal
from pymongo import MongoClient
from pymongo.synchronous.collection import Collection
from pymongo.synchronous.database import Database

from otp.uberdog.persistence.AccountDbBase import AccountDbBase
from otp.uberdog.persistence.AccountLookupResult import AccountLookupResult


class MongoAccountDb(AccountDbBase):
    """
    An account DB that usees Mongo to store play tokens -> Account IDs.
    This class will use its own collection that simply contains documents that map the ID to a DoID to an Account object.
    """
    notify = DirectNotifyGlobal.directNotify.newCategory('MongoAccountDb')

    def __init__(self, gameServicesManager, connectionString):
        super().__init__(gameServicesManager)
        # Connect to the Mongo DB. If we are unsuccessful, this is a SEVERE error. The application cannot continue.

        self._client: MongoClient = MongoClient(connectionString)
        self.notify.debug(f"Successfully initialized MongoAccountDb.")
        self.notify.debug(f"Attempting to connect to Mongo...")
        self._client._connect()
        self.notify.debug(f"Connected to Mongo!")
        self._db: Database[Mapping[str, Any]] = self._client["astrondb"]
        self._tokens: Collection[Mapping[str, Any]] = self._db["playtokens"]
        self.notify.info(f"Successfully initialized Mongo play token store")

    def lookup(self, playToken: str, callback):
        """
        Called when GSM is trying to find an Account associated with a play token.
        We should always call the callback with an AccountLookupResult.
        Also, if an account doesn't exist, we provide the expected defaults if a new account is created.
        """
        self.notify.debug(f"Attempting to look up account token {playToken}")
        doc = self._tokens.find_one({"_id": playToken})
        self.notify.debug(f"Query result: {doc}")
        # If a doc wasn't found, we can cut execution and just return what we would expect from a new account.
        if doc is None:
            self.notify.debug(f"Did not find an account for token {playToken}. Executing callback with defaults.")
            callback(AccountLookupResult(
                success=True,
                accountId=0,  # Acc ID of 0 informs the GSM to create a new account for us.
                databaseId=playToken,
                accessLevel="USER",
                reason="success"
            ))
            return

        # We found a doc, we can query the Astron interface for the associated account.
        # Due to the nature of the database, we ALWAYS expect this account to exist in the account database.
        # If it doesn't, it means something went seriously wrong and we need to manually fix it.
        doId = doc["accountId"]

        self.notify.debug(f"Found account ID {doId} for playToken {playToken}")

        def __account_lookup_callback(dclass, fields):
            """
            The callback that Astron will fire from a query. Kinda ugly, but what can you do...
            """
            # If the returned class isn't an account, our database is fucked.
            if dclass != self.gameServicesManager.air.dclassesByName['AccountUD']:
                self.notify.warning(f"Account lookup failed dclass check. Expected 'AccountUD' for doId {doId} but got '{dclass}'. The database must be repaired for this user.")
                callback(AccountLookupResult(success=False, reason="There was a severe error when looking up your account in the database. Please report this!"))
                return

            # We already have an account object, so we'll just return what we have.
            self.notify.debug(f"Found valid account ID {doId} for playToken {playToken} from the Astron database. Success!")
            callback(AccountLookupResult(
                success=True,
                accountId=doId,
                databaseId=playToken,
                accessLevel=fields.get('ACCESS_LEVEL', 'NO_ACCESS')
            ))

        # Perform a query to find the account with the doId we found in the document.
        self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId, doId, __account_lookup_callback)

    def storeAccountID(self, databaseId, accountId, callback):
        """
        GSM is instructing us to store a certain token to map to a certain account ID.
        We are going to assume the GSM knows what it is doing, so this is considered a dumb operation. If there is
        currently an account already mapped to the desired ID, this will overwrite it.
        """
        self.notify.debug(f"Attempting to store an account mapping for token={databaseId} for account={accountId}")
        try:
            self._tokens.replace_one(
                {"_id": databaseId},
                {"_id": databaseId, "accountId": accountId},
                upsert=True
            )
            self.notify.debug(f"Success! Account ID {accountId} was mapped to {databaseId}.")
            callback(True)
        except Exception as e:
            self.notify.warning(f"Failed to store account ID. {e}")
            callback(False)
