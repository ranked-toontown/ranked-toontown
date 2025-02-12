from direct.directnotify import DirectNotifyGlobal
from panda3d.core import loadPrcFileData
import json

class Settings:
    """
    This is the class that reads JSON formatted settings files, and
    returns the values back to whatever requested them.
    """

    def __init__(self):
        self.fileName = 'dedicated_server_settings.json'
        try:
            with open(self.fileName, 'r') as file:
                self.settings = json.load(file)
        except:
            self.settings = {}

    def getOption(self, type, attribute, default):
        """
        Generic method to fetch the saved configuration settings.
        """
        return self.settings.get(type, {}).get(attribute, default)

    def updateSetting(self, type, attribute, value):
        """
        Update the json file with the new data specified.
        """
        with open(self.fileName, 'w+') as file:
            if not self.settings.get(type):
                self.settings[type] = {}
            self.settings[type][attribute] = value
            json.dump(self.settings, file)

    def getBool(self, type, attribute, default=False):
        """
        Fetch a boolean type from the json file, but use default if it
        returns the incorrect type or doesn't exist.
        """
        value = self.getOption(type, attribute, default)
        if isinstance(value, bool):
            return value
        else:
            return default

class DedicatedServerSettings:
    notify = DirectNotifyGlobal.directNotify.newCategory('DedicatedServerSettings')

    def __init__(self):
        self.settings = Settings()
        self.loadFromSettings()

    def loadFromSettings(self):
        mongoDB = self.settings.getBool('game', 'local-multiplayer', False)
        loadPrcFileData('DedicatedServer Settings Local', 'local-multiplayer %s' % mongoDB)
        self.settings.updateSetting('game', 'local-multiplayer', mongoDB)
