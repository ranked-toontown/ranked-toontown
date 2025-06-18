import dbm
import dbm.dumb

from direct.directnotify import DirectNotifyGlobal

from otp.uberdog.persistence.AccountDbBase import AccountDbBase


class DeveloperAccountDb(AccountDbBase):
    """
    DeveloperAccountDB is a special account database interface implementation designed for use on developer builds of
    the game. This is the default account database interface when running the server locally via source code, which is
    assumed to be a development environment. DeveloperAccountDB accepts a username, and assigns each new user with
    "TTOFF_DEVELOPER" access automatically upon login.
    """
    notify = DirectNotifyGlobal.directNotify.newCategory('DeveloperAccountDB')

    def __init__(self, gameServicesManager):
        super().__init__(gameServicesManager)

        # This uses dbm, so we open the DB file:
        accountDbFile = simbase.config.GetString('accountdb-local-file', 'astron/databases/accounts.db')
        self.dbm = dbm.dumb.open(accountDbFile, 'c')

    def lookup(self, playToken, callback):
        # Check if this play token exists in the dbm:
        if str(playToken) not in self.dbm:
            # It is not, so we'll associate them with a brand new account object.
            callback({'success': True,
                      'accountId': 0,
                      'databaseId': playToken,
                      'accessLevel': "TTOFF_DEVELOPER"})
        else:
            def handleAccount(dclass, fields):
                if dclass != self.gameServicesManager.air.dclassesByName['AccountUD']:
                    result = {'success': False,
                              'reason': 'Your account object (%s) was not found in the database!' % dclass}
                else:
                    # We already have an account object, so we'll just return what we have.
                    result = {'success': True,
                              'accountId': int(self.dbm[playToken]),
                              'databaseId': playToken,
                              'accessLevel': fields.get('ACCESS_LEVEL', 'NO_ACCESS')}

                callback(result)

            self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId,
                                                                 int(self.dbm[playToken]), handleAccount)

    def storeAccountID(self, databaseId, accountId, callback):
        self.dbm[databaseId] = str(accountId)
        if getattr(self.dbm, 'sync', None):
            self.dbm.sync()
            callback(True)
        else:
            self.notify.warning('Unable to associate user %s with account %d!' % (databaseId, accountId))
            callback(False)