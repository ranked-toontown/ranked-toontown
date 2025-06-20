import typing

import uuid as uuidlib
from os import environ

import requests
import time
from datetime import datetime

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobalUD import DistributedObjectGlobalUD
from direct.distributed.PyDatagram import *
from direct.fsm.FSM import FSM

from otp.astron.MsgTypes import *
from otp.distributed import OtpDoGlobals
from otp.otpbase import OTPGlobals


from otp.uberdog.authentication import AuthenticationGlobals
from otp.uberdog.persistence.AccountLookupResult import AccountLookupResult
from otp.uberdog.persistence.DeveloperAccountDb import DeveloperAccountDb
from otp.uberdog.persistence.MongoAccountDb import MongoAccountDb

if typing.TYPE_CHECKING:
    from toontown.toonbase.ToonBaseGlobals import taskMgr


class GameOperation(FSM):
    """
    GameOperation is the base class for all other operations used by the GameServicesManager.
    """
    notify = DirectNotifyGlobal.directNotify.newCategory('GameOperation')
    targetConnection = False

    def __init__(self, gameServicesManager, target):
        FSM.__init__(self, self.__class__.__name__)
        self.gameServicesManager = gameServicesManager
        self.target = target

    def enterOff(self):
        # Deletes the target from either connection2fsm or account2fsm
        # depending on the value of self.targetConnection.
        if self.targetConnection:
            del self.gameServicesManager.connection2fsm[self.target]
        else:
            del self.gameServicesManager.account2fsm[self.target]

    def enterKill(self, reason=''):
        # Kills either the target connection or the target account
        # depending on the value of self.targetConnection, and then
        # sets this FSM's state to Off.
        if self.targetConnection:
            self.gameServicesManager.killConnection(self.target, reason)
        else:
            self.gameServicesManager.killAccount(self.target, reason)

        self.demand('Off')


class DiscordAuthenticateOperation(GameOperation):
    """
    The painful operation of authenticating a user via Discord before allowing a login.
    The idea with this source is that we DO NOT want to store information such as emails and passwords for users,
    since we are a small and uncredible group. This means our login process can only be done in 1 way, where we
    let people login via a play token. This is where Discord OAuth2 comes in to play.

    This operation acts as a middleman in the login process. If Discord OAuth2 is enabled, then we don't accept
    play tokens from connections. We provide them with a unique identifier and tell them to authorize us to log in with
    that identifier using their Discord account. Once we retrieve their Discord ID and verify that it matches with
    the unique identifier and Astron connection, we can use their Discord ID as a play token.

    I would also like to make a developer note on the structure of this class. Usually, I order methods in order of
    public then private methods, but I tried to lay out the order of definitions in this class with the order that
    the code should be executed, due to the callback nature of operations. If you read this class from top to bottom,
    you can expect that the flow of the operation should match.
    """
    notify = DirectNotifyGlobal.directNotify.newCategory('DiscordAuthenticateOperation')
    targetConnection = True

    def __init__(self, gameServicesManager, target, uuid, client, secret, redirect):
        super().__init__(gameServicesManager, target)
        self.uuid = uuid  # The unique "token" we generated that is going to match this auth event with this connection.
        self._clientId = client  # The client ID that is used to build an OAuth2 link
        self._secret = secret  # The client secret that is used to verify an OAuth2 link
        self._redirect = redirect
        self.user: AuthenticationGlobals.DiscordUserInformation | None = None

    def __build_oauth2_link(self) -> str:
        return f"https://discord.com/oauth2/authorize?client_id={self._clientId}&response_type=code&redirect_uri={self._redirect}&scope=identify&state={self.uuid}"

    def __build_redirect_link(self) -> str:
        """
        Formats a redirect link to replace encoded HTTP characters.
        """
        return self._redirect.replace('%2F', '/').replace('%3A', ':')

    def enterStart(self):
        """
        Send the sender how we are handling authentication and a unique identifier that our callback can handle.
        We need to provide the client with that UUID so when they send the authentication link, we know that they
        are the ones that sent it on the backend. Once we receive that authentication hit on our public API from
        their redirect, we can be sure that the connection that is associated with this UUID belongs to the connection
        that authenticated. Since we are mapping server side only connection IDs to this unique ID, even if
        the user were to authenticate from another device via copying the link and going somewhere else, only
        the connection that initiated the process will be able to log in.
        The next step for this operation will occur from Discord forcing a redirect for the user after the
        authentication process that hits our public /auth API with a temporary code that we can use to get tokens.
        """
        # Accept any discord authentication events. We will know if an event affects us if the session matches our UUID.
        # todo: maybe find a way to make this less verbose. very java pilled currently.
        self.accept(AuthenticationGlobals.DiscordAuthenticationEventContext.AUTH_EVENT_IDENTIFIER,
                    self.__handle_discord_auth_event)
        self.notify.debug(f"Starting discord auth operation for sender {self.target} with session {self.uuid}. Waiting for auth response...")

        # Alert the connection of how we authenticate.
        self.gameServicesManager.sendUpdateToChannel(self.target, 'setAuthScheme',
                                                     [self.gameServicesManager.authenticationScheme, self.uuid, self.__build_oauth2_link()])

    def exitStart(self):
        """
        When we exit the start process, we no longer need to listen for authentication events.
        """
        self.notify.debug(f"No longer listening for an authentication event for sender {self.target} with session {self.uuid}")
        self.ignore(AuthenticationGlobals.DiscordAuthenticationEventContext.AUTH_EVENT_IDENTIFIER)

    def __handle_discord_auth_event(self, event: AuthenticationGlobals.DiscordAuthenticationEventContext):
        # If this session doesn't apply to us, don't continue. Just means someone else is authenticating.
        if event.session != self.uuid:
            return

        self.notify.debug(f"Handling discord auth event for sender {self.target} with session {self.uuid}.")

        # If we aren't in a valid state to continue, don't do anything.
        if self.state != 'Start':
            return

        self.notify.debug(f"In correct state, moving on to token retrieval.")
        # This applies to us! The user successfully authenticated. Go to the next step.
        self.demand('RetrieveToken', event.code)
        self.ignore(AuthenticationGlobals.DiscordAuthenticationEventContext.AUTH_EVENT_IDENTIFIER)

    def enterRetrieveToken(self, code: str):
        """
        The user has successfully gone through the OAuth2 process of logging in via their browser, and they have sent
        us a code that we can trade for access/refresh tokens. These tokens can then be utilized to retrieve
        non-sensitive information about their Discord account. All we need to do in this step is send a POST request
        to Discord's API. The result will give us tokens.
        """
        # First, required form data.
        data = {
            'client_id': self._clientId,
            'client_secret': self._secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': f'{self.__build_redirect_link()}'
        }
        # Header information.
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.notify.debug(f"Sending POST request to retrieve access token for session {self.uuid} using code: {code}")
        # Send the response. Make sure to set up a callback when we receive a response.
        AuthenticationGlobals.send_post(
            'https://discord.com/api/v10/oauth2/token',
            data=data,
            headers=headers,
            callback=self.__handle_access_token_response
        )

    def __handle_access_token_response(self, response: requests.Response | None):

        self.notify.debug(f"Received response from POST request to retrieve access token for session {self.uuid}.")

        # If we aren't in a valid state to continue, don't do anything.
        # This can happen if our operation gets killed in the middle of an HTTP request.
        if self.state != 'RetrieveToken':
            return

        if response is None:
            self.demand("Kill", "Failed to communicate with Discord's authentication API. Try again later.")
            return

        self.notify.debug(f"Received response from access token request with a status code of {response.status_code} reason={response.reason}")

        # If the response is None, that means this operation is toast. Cancel.
        if response.status_code != 200:
            self.notify.warning(f"failed to retrieve access tokens - response: {response.json()}")
            self.demand('Kill', "Failed to retrieve authentication token from Discord. Is the API down?")
            return

        self.notify.debug(f"In correct state, moving on to information retrieval.")

        # Let's go to the next step.
        self.demand('RetrieveInformation', response)

    def enterRetrieveInformation(self, response: requests.Response):
        """
        Called once we receive a successful response from Discord when trying to trade a code for access tokens.
        Sends a new request to Discord that queries user information using their access token.
        """
        # The data we received contains an access token. Use this token to query information about them.
        data = response.json()
        token = data['access_token']
        headers = {
            'Authorization': f"Bearer {token}"
        }

        self.notify.debug(f"Sending GET request to retrieve information about access token for session {self.uuid}.")
        self.notify.debug(f"Full data: {data}")
        # Fire and forget a GET response to query information about the user using their authentication token.
        AuthenticationGlobals.send_get(
            'https://discord.com/api/v10/oauth2/@me',
            headers=headers,
            callback=self.__handle_discord_information_response
        )

    def __handle_discord_information_response(self, response: requests.Response | None):

        self.notify.debug(f"Handling Discord information response for session {self.uuid}.")

        # If we aren't in a valid state to continue, don't do anything.
        # This can happen if our operation gets killed in the middle of an HTTP request.
        if self.state != 'RetrieveInformation':
            return

        self.notify.debug(f"Received response from information request with a status code of {response.status_code} reason={response.reason}")

        # If the response is None, that means this operation is toast. Cancel.
        if response is None or response.status_code != 200:
            self.notify.warning(f"failed to retrieve discord information - response: {response.json()}")
            self.demand('Kill', "Failed to retrieve user information from Discord. Is the API down?")
            return

        self.notify.debug(f"In correct state, moving on to information parsing.")

        # Next step!
        self.demand('GotInformation', response)

    def enterGotInformation(self, response: requests.Response):
        """
        This response should contain information about the user! Now that we have Discord information to associate
        with this session and connection, we can now move on to the normal login stage. Finally.
        This call will clean up this operation. Afterward, we can schedule the new one.
        """
        # Clean up this operation. We are done.
        self.notify.debug(f"Successfully authenticated and extracted information. Cleaning up Authentication operation...")

        # Queue up a new login operation, using the discord ID as the play token. todo
        # We have their discord ID! This is also a valid state in authentication. We can simply use their
        # Discord ID as a play token. Additionally, we can also keep track of other data related to their account.
        data = response.json()
        _id = data['user']["id"]
        username = data['user']["username"]
        pfp = data['user']["avatar"]
        self.user = AuthenticationGlobals.DiscordUserInformation(_id, username, pfp)
        self.notify.debug(f"Parsed discord information for session {self.uuid}: id={_id} - username={username} - pfp={pfp}")
        self.notify.debug(f"Information parsed: {data}")

        # Clean up this operation. Since a user is set, it will attempt to transition to the login event.
        self.demand("Off")
        
    def enterOff(self):
        """
        When this operation is done, we no longer need to worry about timing it out.
        """
        super().enterOff()
        taskMgr.remove(f"discord-auth-timeout-{self.target}")

        if self.user is not None:
            self.notify.debug(f"User information is defined! Queueing up a Login operation...")
            self.gameServicesManager.startLoginWithPlaytoken(self.target, self.user.userId)


class LoginOperation(GameOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('LoginOperation')
    targetConnection = True

    def __init__(self, gameServicesManager, target):
        GameOperation.__init__(self, gameServicesManager, target)
        self.playToken = None
        self.account = None

    def enterStart(self, playToken):
        # Sets self.playToken, then enters the QueryAccountDB state.
        self.playToken = playToken
        self.demand('QueryAccountDB')

    def enterQueryAccountDB(self):
        # Calls the lookup function on the GameServicesManager's defined account DB interface.
        self.gameServicesManager.accountDb.lookup(self.playToken, self.__handleLookup)

    def __handleLookup(self, result: AccountLookupResult):
        # This is a callback function that will be called by the lookup function
        # of the GameServicesManager's account DB interface. It processes the
        # lookup function's result & determines which operation should run next.
        self.notify.debug(f"Received lookup result: {result}")
        if not result.success:
            # The play token was rejected! Kill the connection.
            self.gameServicesManager.air.writeServerEvent('play-token-rejected', self.target, self.playToken)
            self.notify.warning(f"Rejecting play token {self.playToken}.")
            self.demand('Kill', result.reason)
            return

        # Grab the databaseId, accessLevel, and accountId from the result.
        self.databaseId = result.databaseId
        self.accessLevel = result.accessLevel
        accountId = result.accountId
        self.notify.debug(f"Entering account retrieval/creation process with dbId={self.databaseId} accessLevel={self.accessLevel} accId{accountId}.")

        if accountId:
            # There is an account ID, so let's retrieve the associated account.
            self.accountId = accountId
            self.notify.debug(f"Account ID is not 0. Retrieve the account with ID {accountId}.")
            self.demand('RetrieveAccount')
        else:
            # There is no account ID, so let's create a new account.
            self.notify.debug(f"Account ID is 0. Create a new account.")
            self.demand('CreateAccount')

    def enterCreateAccount(self):
        # Creates a brand new account & stores it in the database.
        self.account = {'ACCOUNT_AV_SET': [0] * 6,
                        'ESTATE_ID': 0,
                        'ACCOUNT_AV_SET_DEL': [],
                        'CREATED': time.ctime(),
                        'LAST_LOGIN': time.ctime(),
                        'ACCOUNT_ID': str(self.databaseId),
                        'ACCESS_LEVEL': self.accessLevel}

        self.notify.debug(f"Creating account with data {self.account}")
        # Create the account object in the database using the data from self.account.
        # self.__handleCreate is the callback which will be called after createObject has completed.
        self.gameServicesManager.air.dbInterface.createObject(self.gameServicesManager.air.dbId,
                                                              self.gameServicesManager.air.dclassesByName['AccountUD'],
                                                              self.account, self.__handleCreate)

    def __handleCreate(self, accountId):

        self.notify.debug(f"Account creation process for account {accountId}")

        # This function handles successful & unsuccessful account creations.
        if self.state != 'CreateAccount':
            # If we're not in the CreateAccount state, this request is invalid.
            self.notify.warning('Received CreateAccount response outside of the CreateAccount state.')
            return

        if not accountId:
            # If we don't have an accountId, then that means the database was unable
            # to create an account object for us, for whatever reason. Kill the connection.
            self.notify.warning('Database failed to create an account object!')
            self.demand('Kill', 'Your account object could not be created in the game database.')
            return

        # Otherwise, the account object was created successfully!
        self.gameServicesManager.air.writeServerEvent('account-created', accountId)

        # We can now enter the StoreAccountID state.
        self.accountId = accountId
        self.demand('StoreAccountID')

    def enterStoreAccountID(self):
        # Stores the account ID in the account bridge.
        # self.__handleStored is the callback which
        # will be called after storeAccountID has completed.
        self.gameServicesManager.accountDb.storeAccountID(self.databaseId, self.accountId, self.__handleStored)

    def __handleStored(self, success=True):
        if not success:
            # The account bridge was unable to store the account ID,
            # for whatever reason. Kill the connection.
            self.demand('Kill', 'The account server could not save your account DB ID!')
            return

        # We are all set with account creation now! It's time to enter the SetAccount state.
        self.demand('SetAccount')

    def enterRetrieveAccount(self):
        # Query the database object associated with self.accountId.
        # self.__handleRetrieve is the callback which will be called
        # after queryObject has completed.
        self.notify.debug(f"Entering account retrieval process. Querying for account {self.accountId}")
        self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId, self.accountId,
                                                             self.__handleRetrieve)

    def __handleRetrieve(self, dclass, fields):
        # Checks if the queried object is valid and if it is, enters
        # the SetAccount state. Otherwise, the connection is killed.
        if dclass != self.gameServicesManager.air.dclassesByName['AccountUD']:
            # This is not an account object! Kill the connection.
            self.notify.warning(f'Object class associated with account {self.accountId} is not an AccountUD object. It is {dclass}')
            self.demand('Kill', 'Your account object (%s) was not found in the database!' % dclass)
            return

        # We can now enter the SetAccount state.
        self.notify.debug(f"Entering SetAccount phase. Successfully queried account.")
        self.account = fields
        self.demand('SetAccount')

    def enterSetAccount(self):
        # If somebody's already logged into this account, disconnect them.
        datagram = PyDatagram()
        datagram.addServerHeader(self.gameServicesManager.GetAccountConnectionChannel(self.accountId),
                                 self.gameServicesManager.air.ourChannel, CLIENTAGENT_EJECT)
        datagram.addUint16(OTPGlobals.BootedLoggedInElsewhere)
        datagram.addString('This account has been logged into elsewhere.')
        self.gameServicesManager.air.send(datagram)

        # Now we'll add this connection to the account channel.
        datagram = PyDatagram()
        datagram.addServerHeader(self.target, self.gameServicesManager.air.ourChannel, CLIENTAGENT_OPEN_CHANNEL)
        datagram.addChannel(self.gameServicesManager.GetAccountConnectionChannel(self.accountId))
        self.gameServicesManager.air.send(datagram)

        # Set their sender channel to represent their account affiliation.
        datagram = PyDatagram()
        datagram.addServerHeader(self.target, self.gameServicesManager.air.ourChannel, CLIENTAGENT_SET_CLIENT_ID)
        datagram.addChannel(self.accountId << 32)  # accountId in high 32 bits, 0 in low (no avatar).
        self.gameServicesManager.air.send(datagram)

        # We can now un-sandbox the sender.
        self.gameServicesManager.air.setClientState(self.target, 2)  # ESTABLISHED state.

        # Update the last login timestamp.
        self.gameServicesManager.air.dbInterface.updateObject(self.gameServicesManager.air.dbId, self.accountId,
                                                              self.gameServicesManager.air.dclassesByName['AccountUD'],
                                                              {'LAST_LOGIN': time.ctime(),
                                                               'ACCOUNT_ID': str(self.databaseId),
                                                               'ACCESS_LEVEL': self.accessLevel})

        # We're done.
        self.gameServicesManager.air.writeServerEvent('account-login', clientId=self.target, accId=self.accountId,
                                                      dbId=self.databaseId, playToken=self.playToken)

        # Send the acceptLogin update through the GameServicesManager & set this operation's state to Off.
        self.gameServicesManager.sendUpdateToChannel(self.target, 'acceptLogin', [])
        self.demand('Off')


class AvatarOperation(GameOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('AvatarOperation')
    postAccountState = 'Off'  # Must be overridden by subclass.

    def enterRetrieveAccount(self):
        # Query the account. self.__handleRetrieve is the callback
        # which will be called after queryObject has completed.
        self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId, self.target,
                                                             self.__handleRetrieve)

    def __handleRetrieve(self, dclass, fields):
        if dclass != self.gameServicesManager.air.dclassesByName['AccountUD']:
            # This is not an account object! Kill the connection.
            self.notify.warning(f"Failed to query for {self.target}'s avatars. The dclass is not an AccountUD! It is {dclass}")
            self.demand('Kill', 'Your account object (%s) was not found in the database!' % dclass)
            return

        # Set the account & avList.
        self.account = fields
        self.avList = self.account['ACCOUNT_AV_SET']

        # Sanitize the avList, just in case it is too long/short.
        self.avList = self.avList[:6]
        self.avList += [0] * (6 - len(self.avList))

        # We're done; enter the postAccountState.
        self.demand(self.postAccountState)


class GetAvatarsOperation(AvatarOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('GetAvatarsOperation')
    postAccountState = 'QueryAvatars'

    def __init__(self, gameServicesManager, target):
        AvatarOperation.__init__(self, gameServicesManager, target)
        self.pendingAvatars = None
        self.avatarFields = None

    def enterStart(self):
        # First, retrieve the account.
        self.demand('RetrieveAccount')

    def enterQueryAvatars(self):
        # Now, we will query the avatars that exist in the account.
        self.pendingAvatars = set()
        self.avatarFields = {}

        # Loop through the list of avatars:
        for avId in self.avList:
            if avId:
                # This index contains an avatar! Add it to the pending avatars.
                self.pendingAvatars.add(avId)

                # This is our callback function that queryObject
                # will call when done querying each avatar object.
                def response(dclass, fields, avId=avId):
                    if self.state != 'QueryAvatars':
                        # We're not in the QueryAvatars state, so this request is invalid.
                        return

                    if dclass != self.gameServicesManager.air.dclassesByName[self.gameServicesManager.avatarDclass]:
                        # The dclass is invalid! Kill the connection.
                        self.demand('Kill', 'One of the account\'s avatars is invalid! dclass = %s, expected = %s' % (
                            dclass, self.gameServicesManager.avatarDclass))
                        return

                    # Otherwise, we're all set! Add the queried avatar fields to the
                    # avatarFields array, remove from the pending list, and set our
                    # state to SendAvatars.
                    self.avatarFields[avId] = fields
                    self.pendingAvatars.remove(avId)
                    if not self.pendingAvatars:
                        self.demand('SendAvatars')

                # Query the avatar object.
                self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId, avId, response)

        if not self.pendingAvatars:
            # No pending avatars! Set our state to SendAvatars.
            self.demand('SendAvatars')

    def enterSendAvatars(self):
        # Here is where we'll construct a list of potential avatars,
        # given the data from self.avatarFields, and send that to the client.
        potentialAvatars = []

        # Loop through the avatarFields array:
        for avId, fields in list(self.avatarFields.items()):
            # Get the appropriate values.
            index = self.avList.index(avId)
            wishNameState = fields.get('WishNameState', [''])[0]
            name = fields['setName'][0]
            nameState = 0
            if wishNameState == 'OPEN':
                nameState = 1
            elif wishNameState == 'PENDING':
                nameState = 2
            elif wishNameState == 'APPROVED':
                nameState = 3
                name = fields['WishName'][0]
            elif wishNameState == 'REJECTED':
                nameState = 4
            elif wishNameState == 'LOCKED':
                nameState = 0
            else:
                self.gameServicesManager.notify.warning(
                    'Avatar %s is in unknown name state %s.' % (avId, wishNameState))
                nameState = 0

            # Add those to potentialAvatars.
            potentialAvatars.append([avId, name, fields['setDNAString'][0], index, nameState])

        # We're done; send the avatarListResponse update through the
        # GameServicesManager, then we can set this operation's
        # state to Off.
        self.gameServicesManager.sendUpdateToAccountId(self.target, 'avatarListResponse', [potentialAvatars])
        self.demand('Off')


# n.b.: We inherit from GetAvatarsOperation here as the remove
# operation ends in a setAvatars message being sent to the client.
class RemoveAvatarOperation(GetAvatarsOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('RemoveAvatarOperation')
    postAccountState = 'ProcessRemove'

    def __init__(self, gameServicesManager, target):
        GetAvatarsOperation.__init__(self, gameServicesManager, target)
        self.avId = None

    def enterStart(self, avId):
        # Store this value & call the base function.
        self.avId = avId
        GetAvatarsOperation.enterStart(self)

    def enterProcessRemove(self):
        # Make sure that the target avatar is part of the account:
        if self.avId not in self.avList:
            # The sender tried to remove an avatar not on the account! Kill the connection.
            self.demand('Kill', 'Tried to remove an avatar not on the account!')
            return

        # Get the index of this avatar.
        index = self.avList.index(self.avId)
        self.avList[index] = 0

        # We will now add this avatar to ACCOUNT_AV_SET_DEL.
        avatarsRemoved = list(self.account.get('ACCOUNT_AV_SET_DEL', []))
        avatarsRemoved.append([self.avId, int(time.time())])

        # Get the estate ID of this account.
        estateId = self.account.get('ESTATE_ID', 0)

        if estateId != 0:
            # The following will assume that the house already exists,
            # however it shouldn't be a problem if it doesn't.
            self.gameServicesManager.air.dbInterface.updateObject(self.gameServicesManager.air.dbId, estateId,
                                                                  self.gameServicesManager.air.dclassesByName[
                                                                      'DistributedEstateAI'],
                                                                  {'setSlot%sToonId' % index: [0],
                                                                   'setSlot%sItems' % index: [[]]})

        if self.gameServicesManager.air.onlinePlayerManager:
            self.gameServicesManager.air.onlinePlayerManager.clearList(self.avId)
        else:
            friendsManagerDoId = OtpDoGlobals.OTP_DO_ID_ONLINE_PLAYER_MANAGER
            friendsManagerDclass = self.gameServicesManager.air.dclassesByName['OnlinePlayerManagerUD']
            datagram = friendsManagerDclass.aiFormatUpdate('clearList', friendsManagerDoId, friendsManagerDoId,
                                                           self.gameServicesManager.air.ourChannel, [self.avId])
            self.gameServicesManager.air.send(datagram)

        # We can now update the account with the new data. self.__handleRemove is the
        # callback which will be called upon completion of updateObject.
        self.gameServicesManager.air.dbInterface.updateObject(self.gameServicesManager.air.dbId, self.target,
                                                              self.gameServicesManager.air.dclassesByName['AccountUD'],
                                                              {'ACCOUNT_AV_SET': self.avList,
                                                               'ACCOUNT_AV_SET_DEL': avatarsRemoved},
                                                              {'ACCOUNT_AV_SET': self.account['ACCOUNT_AV_SET'],
                                                               'ACCOUNT_AV_SET_DEL': self.account[
                                                                   'ACCOUNT_AV_SET_DEL']},
                                                              self.__handleRemove)

    def __handleRemove(self, fields):
        if fields:
            # The avatar was unable to be removed from the account! Kill the account.
            self.demand('Kill', 'Database failed to mark the avatar as removed!')
            return

        # Otherwise, we're done! We'll enter the QueryAvatars state now so that
        # the user is sent back to the avatar chooser.
        self.gameServicesManager.air.writeServerEvent('avatar-deleted', self.avId, self.target)
        self.demand('QueryAvatars')


class LoadAvatarOperation(AvatarOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('LoadAvatarOperation')
    postAccountState = 'GetTargetAvatar'

    def __init__(self, gameServicesManager, target):
        AvatarOperation.__init__(self, gameServicesManager, target)
        self.avId = None

    def enterStart(self, avId):
        # Store this value & move on to RetrieveAccount
        self.avId = avId
        self.demand('RetrieveAccount')

    def enterGetTargetAvatar(self):
        # Make sure that the target avatar is part of the account:
        if self.avId not in self.avList:
            # The sender tried to play on an avatar not on the account! Kill the connection.
            self.demand('Kill', 'Tried to play on an avatar not on the account!')
            return

        # Query the database for the avatar. self.__handleAvatar is
        # our callback which will be called upon queryObject's completion.
        self.gameServicesManager.air.dbInterface.queryObject(self.gameServicesManager.air.dbId, self.avId,
                                                             self.__handleAvatar)

    def __handleAvatar(self, dclass, fields):
        if dclass != self.gameServicesManager.air.dclassesByName[self.gameServicesManager.avatarDclass]:
            # This dclass is not a valid avatar! Kill the connection.
            self.demand('Kill', 'One of the account\'s avatars is invalid!')
            return

        # Store the avatar & move on to SetAvatar.
        self.avatar = fields
        self.demand('SetAvatar')

    def enterSetAvatar(self):
        # Get the client channel.
        channel = self.gameServicesManager.GetAccountConnectionChannel(self.target)

        # We will first assign a POST_REMOVE that will unload the
        # avatar in the event of them disconnecting while we are working.
        cleanupDatagram = PyDatagram()
        cleanupDatagram.addServerHeader(self.avId, channel, STATESERVER_OBJECT_DELETE_RAM)
        cleanupDatagram.addUint32(self.avId)
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_ADD_POST_REMOVE)
        datagram.addUint16(cleanupDatagram.getLength())
        datagram.appendData(cleanupDatagram.getMessage())
        self.gameServicesManager.air.send(datagram)

        # We will now set the account's days since creation on the client.
        creationDate = self.getCreationDate()
        accountDays = -1
        if creationDate:
            now = datetime.fromtimestamp(time.mktime(time.strptime(time.ctime())))
            accountDays = abs((now - creationDate).days)

        if accountDays < 0 or accountDays > 4294967295:
            accountDays = 100000

        self.gameServicesManager.sendUpdateToAccountId(self.target, 'receiveAccountDays', [accountDays])

        # Get the avatar's "true" access (that is, the integer value that corresponds to the assigned string value).
        accessLevel = self.account.get('ACCESS_LEVEL', 'NO_ACCESS')
        accessLevel = OTPGlobals.accessLevelValues.get(accessLevel, 0)

        # We will now activate the avatar on the DBSS.
        self.gameServicesManager.air.sendActivate(self.avId, 0, 0, self.gameServicesManager.air.dclassesByName[
            self.gameServicesManager.avatarDclass], {'setAccessLevel': [accessLevel]})

        # Next, we will add them to the avatar channel.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_OPEN_CHANNEL)
        datagram.addChannel(self.gameServicesManager.GetPuppetConnectionChannel(self.avId))
        self.gameServicesManager.air.send(datagram)

        # We will now set the avatar as the client's session object.
        self.gameServicesManager.air.clientAddSessionObject(channel, self.avId)

        # Now we need to set their sender channel to represent their account affiliation.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_SET_CLIENT_ID)
        datagram.addChannel(self.target << 32 | self.avId)  # accountId in high 32 bits, avatar in low.
        self.gameServicesManager.air.send(datagram)

        # We will now grant ownership.
        self.gameServicesManager.air.setOwner(self.avId, channel)

        # Tell the friends manager that an avatar is coming online.
        name = self.avatar['setName'][0]
        dna = self.avatar['setDNAString'][0]
        self.gameServicesManager.air.onlinePlayerManager.comingOnline(self.avId, name, dna)

        # Now we'll assign a POST_REMOVE that will tell the friends manager
        # that an avatar has gone offline, in the event that they disconnect
        # unexpectedly.
        if self.gameServicesManager.air.onlinePlayerManager:
            friendsManagerDclass = self.gameServicesManager.air.onlinePlayerManager.dclass
            cleanupDatagram = friendsManagerDclass.aiFormatUpdate('goingOffline',
                                                                  self.gameServicesManager.air.onlinePlayerManager.doId,
                                                                  self.gameServicesManager.air.onlinePlayerManager.doId,
                                                                  self.gameServicesManager.air.ourChannel, [self.avId, self.target])
        else:
            friendsManagerDoId = OtpDoGlobals.OTP_DO_ID_ONLINE_PLAYER_MANAGER
            friendsManagerDclass = self.gameServicesManager.air.dclassesByName['OnlinePlayerManagerUD']
            cleanupDatagram = friendsManagerDclass.aiFormatUpdate('goingOffline', friendsManagerDoId,
                                                                  friendsManagerDoId,
                                                                  self.gameServicesManager.air.ourChannel, [self.avId, self.target])

        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_ADD_POST_REMOVE)

        datagram.addUint16(cleanupDatagram.getLength())
        datagram.appendData(cleanupDatagram.getMessage())
        self.gameServicesManager.air.send(datagram)

        # We can now finally shut down this operation.
        self.gameServicesManager.air.writeServerEvent('avatar-chosen', avId=self.avId, accId=self.target)
        self.demand('Off')

    def getCreationDate(self):
        # Based on game creation date:
        creationDate = self.account.get('CREATED', '')
        try:
            creationDate = datetime.fromtimestamp(time.mktime(time.strptime(creationDate)))
        except ValueError:
            creationDate = ''

        return creationDate


class UnloadAvatarOperation(GameOperation):
    notify = DirectNotifyGlobal.directNotify.newCategory('UnloadAvatarOperation')

    def __init__(self, gameServicesManager, target):
        GameOperation.__init__(self, gameServicesManager, target)
        self.avId = None

    def enterStart(self, avId):
        # Store the avId.
        self.avId = avId

        # We actually don't even need to query the account, as we know
        # that the avatar is being played, so let's just unload the avatar.
        self.demand('UnloadAvatar')

    def enterUnloadAvatar(self):
        # Get the client channel.
        channel = self.gameServicesManager.GetAccountConnectionChannel(self.target)

        # Tell the friends manager that we're logging off.
        self.gameServicesManager.air.onlinePlayerManager.goingOffline(self.avId, self.target)

        # First, remove our POST_REMOVES.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_CLEAR_POST_REMOVES)
        self.gameServicesManager.air.send(datagram)

        # Next, remove the avatar channel.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_CLOSE_CHANNEL)
        datagram.addChannel(self.gameServicesManager.GetPuppetConnectionChannel(self.avId))
        self.gameServicesManager.air.send(datagram)

        # Next, reset the sender channel.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_SET_CLIENT_ID)
        datagram.addChannel(self.target << 32)  # accountId in high 32 bits, no avatar in low.
        self.gameServicesManager.air.send(datagram)

        # Reset the session object.
        datagram = PyDatagram()
        datagram.addServerHeader(channel, self.gameServicesManager.air.ourChannel, CLIENTAGENT_REMOVE_SESSION_OBJECT)
        datagram.addUint32(self.avId)
        self.gameServicesManager.air.send(datagram)

        # Unload the avatar object.
        datagram = PyDatagram()
        datagram.addServerHeader(self.avId, channel, STATESERVER_OBJECT_DELETE_RAM)
        datagram.addUint32(self.avId)
        self.gameServicesManager.air.send(datagram)

        # We're done! We can now shut down this operation.
        self.gameServicesManager.air.writeServerEvent('avatar-unloaded', avId=self.avId)
        self.demand('Off')


class GameServicesManagerUD(DistributedObjectGlobalUD):
    notify = DirectNotifyGlobal.directNotify.newCategory('GameServicesManagerUD')
    avatarDclass = None  # Must be overridden by subclass.

    def __init__(self, air):
        DistributedObjectGlobalUD.__init__(self, air)
        self._clientId = environ.get('DISCORD_APP_CLIENT_ID', None)
        self._clientSecret = environ.get('DISCORD_APP_CLIENT_SECRET', None)
        self._clientRedirect = environ.get('DISCORD_APP_CLIENT_REDIRECT', None)
        self._playtokenStrategy = environ.get('DISCORD_PLAYTOKENSTRATEGY', 'FILESYSTEM')
        self.connection2fsm = {}
        self.account2fsm = {}
        self.accountDb = None

        # The authentication scheme you want the server to use. You may only use one. The following options are as follows:
        # AUTHENTICATION_SCHEME_DISCORD: Usernameless/Passwordless/Emailless login. Users login by clicking a link.
        # AUTHENTICATION_SCHEME_DEVTOKEN: Users login by providing a username. No passwords/emails involved, your username is essentially your login password.
        _authScheme = environ.get('AUTHENTICATION_SCHEME', 'DEVTOKEN')
        self.authenticationScheme = None
        if _authScheme == 'DEVTOKEN':
            self.authenticationScheme = AuthenticationGlobals.AUTHENTICATION_SCHEME_DEVTOKEN
        elif _authScheme == 'DISCORDOAUTH2':
            self.authenticationScheme = AuthenticationGlobals.AUTHENTICATION_SCHEME_DISCORD

        # If an auth scheme was unresolved, default to devtoken. Print out a warning though just in case.
        if self.authenticationScheme is None:
            self.notify.warning(f"Did not detect a valid authentication scheme. Defaulting to DEVTOKEN. Please be sure to double check your configuration.")
            self.authenticationScheme = AuthenticationGlobals.AUTHENTICATION_SCHEME_DEVTOKEN

        # This is an important step and a fatal configuration issue if this occurs.
        # If we are using discord authentication but have no OAuth2 environment variables set, make the application throw.
        if self.authenticationScheme == AuthenticationGlobals.AUTHENTICATION_SCHEME_DISCORD:
            if None in (self._clientId, self._clientSecret, self._clientRedirect):
                self.notify.error(f"OAuth2 authentication scheme is enabled but you are missing values for either your client ID, client secret, or redirect URI. Check your configuration and try again!")
                raise Exception(f"OAuth2 authentication scheme is enabled but you are missing values for either your client ID, client secret, or redirect URI. Check your configuration and try again!")

        # If the client secret and ID are STILL None, it means they are unneeded. Ensure they aren't None so Astron doesn't freak out.
        if self._clientId is None:
            self._clientId = ''
        if self._clientSecret is None:
            self._clientSecret = ''
        if self._clientRedirect is None:
            self._clientRedirect = ''

    def announceGenerate(self):
        DistributedObjectGlobalUD.announceGenerate(self)

        # The purpose of connection2fsm & account2fsm are to
        # keep track of the connection & account IDs that are
        # currently running an operation on the GameServicesManager.
        # Ideally, this will help us prevent clients from running
        # more than one operation at a time which could potentially
        # lead to race conditions & the exploitation of them.
        self.connection2fsm = {}
        self.account2fsm = {}

        # Instantiate the account database interface.
        # If we have Mongo credentials set, we can assume we want to use MongoDB. Otherwise, just use Dev DB.
        credentials = environ.get('MONGO_CONNECTION_STRING', None)
        if self._playtokenStrategy == 'MONGODB':
            if credentials is None:
                self.notify.error(f"Your configuration is invalid. If you want to use MongoDB for playtokens, you must provide the `MONGO_CONNECTION_STRING` environment variable.")
                exit(1)
            self.accountDb = MongoAccountDb(self, credentials)
        else:
            self.accountDb = DeveloperAccountDb(self)

    def requestAuthScheme(self):
        """
        Called from a client. They would like to know our authentication scheme. Associate this connection with
        a short-lived identifier so we can map an OAuth2 callback with them. This will also trigger the
        "Authentication" process in the login flow, which happens before actually logging them in.
        """
        sender = self.air.getMsgSender()

        # Create a new UUID and associate it with this sender.
        uuid: uuidlib.UUID = uuidlib.uuid4()
        self.notify.debug(f"Started new authentication session with {sender}. Their session ID is {uuid}")
        taskMgr.doMethodLater(5 * 60, self.__timeoutAuthenticationProcess, f"discord-auth-timeout-{sender}", extraArgs=[sender])  # Expire this process after 5 min.
        self.notify.debug(f"Authentication session will time out in 5 minutes.")

        # If we are not using OAuth2, we can simply just tell the user we are using normal logins.
        if self.authenticationScheme == AuthenticationGlobals.AUTHENTICATION_SCHEME_DEVTOKEN:
            self.sendUpdateToChannel(sender, 'setAuthScheme',[self.authenticationScheme, str(uuid), ''])
            return

        # This operation starts in a floating limbo state, while we wait for the user to authenticate.
        self.connection2fsm[sender] = DiscordAuthenticateOperation(self, sender, str(uuid), self._clientId, self._clientSecret, self._clientRedirect)
        self.connection2fsm[sender].request('Start')

    def __timeoutAuthenticationProcess(self, sender, _=None):
        """
        Called internally when we want to expire an authentication process. Only will do anything if there is
        currently an authentication procedure in progress for the given sender.
        """
        if sender not in self.connection2fsm:
            return

        # If the current operation isn't an auth operation, don't worry about it.
        operation = self.connection2fsm[sender]
        if not isinstance(operation, DiscordAuthenticateOperation):
            return

        operation.request("Kill", "Timed out waiting for authentication.")

    def login(self, playToken):
        """
        Called via an astron update from clients. They provide a play token for us to check against.
        When they provide us this token, we need to see if it associates with an account.
        Note that this will only work if we are entrusting clients with their own play tokens. If we are using
        a method of OAuth2 to authenticate, we do not log in clients via this method.
        """
        # Get the connection ID.
        sender = self.air.getMsgSender()

        self.notify.debug('Play token %s received from %s' % (playToken, sender))

        if sender >> 32:
            # This account is already logged in.
            self.killConnection(sender, 'This account is already logged in.')
            return

        if sender in self.connection2fsm:
            # This account is already currently running an operation. Kill this connection.
            self.killConnectionFSM(sender)
            return

        if self.authenticationScheme != AuthenticationGlobals.AUTHENTICATION_SCHEME_DEVTOKEN:
            # If this fires, this is low-key suspicious. We gave them the authentication scheme. Why are they trying to
            # log in using their own play token when we told them we aren't using them?
            self.killConnection(sender, "Authentication failed. Are your files out of date?")
            return

        # Run the normal login operation.
        self.startLoginWithPlaytoken(sender, playToken)

    def startLoginWithPlaytoken(self, sender, token):
        """
        Starts the login process with a given token. If we are not in a valid state for this connection to login,
        nothing will happen. Ensure the following conditions are met before calling this method:
        - There is currently not an operation running for the connection (sender).
        - The token is a play token you trust. If you are authenticating via OAuth2, it needs to be checked to be valid.
        - You are sure you are fine with the given sender logging in using the given token.
        """
        # Run the normal login operation.
        self.notify.debug(f"Attempting login operation for sender {sender} with token {token}")

        # If we are in the middle of an authentication operation, and we are in a valid state to login, clean it up.
        operation = self.connection2fsm.get(sender)
        if isinstance(operation, DiscordAuthenticateOperation):
            self.notify.debug(f"Connection {sender} was in the middle of authentication and tried to login.")
            if operation.state == "GotInformation":
                self.notify.debug(f"They were in a valid state to proceed. Clean up auth operation.")
                operation.demand("Off")
            else:
                self.notify.debug(f"They were not ready to login. Don't do anything. Current state: {operation.state}")
                return

        self.notify.debug(f"Starting login operation for {sender}. Currently running operation? {sender in self.connection2fsm}")
        self.connection2fsm[sender] = LoginOperation(self, sender)
        self.connection2fsm[sender].request('Start', token)

    def killConnection(self, connectionId, reason):
        # Sends CLIENTAGENT_EJECT to the given connectionId with the given reason.
        datagram = PyDatagram()
        datagram.addServerHeader(connectionId, self.air.ourChannel, CLIENTAGENT_EJECT)
        datagram.addUint16(OTPGlobals.BootedConnectionKilled)
        datagram.addString(reason)
        self.air.send(datagram)

    def killConnectionFSM(self, connectionId):
        # Kills the connection for duplicate FSMs.
        fsm = self.connection2fsm.get(connectionId)
        if not fsm:
            self.notify.warning('Tried to kill connection %s for duplicate FSMs, but none exist!' % connectionId)
            return

        self.killConnection(connectionId, 'An operation is already running: %s' % fsm.name)

    def killAccount(self, accountId, reason):
        # Kills the account's connection given an accountId & a reason.
        self.killConnection(self.GetAccountConnectionChannel(accountId), reason=reason)

    def killAccountFSM(self, accountId):
        # Kills the account for duplicate FSMs.
        fsm = self.account2fsm.get(accountId)
        if not fsm:
            self.notify.warning('Tried to kill account %s for duplicate FSMs, but none exist!' % accountId)
            return

        self.killAccount(accountId, 'An operation is already running: %s' % fsm.name)

    def runOperation(self, operationType, *args):
        # Runs an operation on the sender. First, get the sender.
        sender = self.air.getAccountIdFromSender()

        if not sender:
            # If the sender doesn't exist, they're not
            # logged in, so kill the connection.
            self.killAccount(sender, 'Client is not logged in.')

        if sender in self.account2fsm:
            # This account is already currently running an operation. Kill this connection.
            self.killAccountFSM(sender)
            return

        self.account2fsm[sender] = operationType(self, sender)
        self.account2fsm[sender].request('Start', *args)

    def requestAvatarList(self):
        # An account is requesting their avatar list;
        # let's run a GetAvatarsOperation.
        self.runOperation(GetAvatarsOperation)

    def requestRemoveAvatar(self, avId):
        # Someone is requesting to have an avatar removed; run a RemoveAvatarOperation.
        self.runOperation(RemoveAvatarOperation, avId)

    def requestPlayAvatar(self, avId):
        # Someone is requesting to play on an avatar.
        # First, let's get the senders avId & accId.
        currentAvId = self.air.getAvatarIdFromSender()
        accountId = self.air.getAccountIdFromSender()
        if currentAvId and avId:
            # An avatar has already been chosen! Kill the account.
            self.killAccount(accountId, 'An avatar is already chosen!')
            return
        elif not currentAvId and not avId:
            # The client is likely making sure that none of its
            # avatars are active, so this isn't really an error.
            return

        if avId:
            # If the avId is not a NoneType, that means the client wants
            # to load an avatar; run a LoadAvatarOperation.
            self.runOperation(LoadAvatarOperation, avId)
        else:
            # Otherwise, the client wants to unload the avatar; run an UnloadAvatarOperation.
            self.runOperation(UnloadAvatarOperation, currentAvId)
