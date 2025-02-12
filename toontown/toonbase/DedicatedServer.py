import os
import sys
import time
import atexit
import subprocess
from panda3d.core import ConfigVariableString, ConfigVariableBool

from direct.directnotify import DirectNotifyGlobal
from otp.otpbase import OTPLocalizer

AI_NOITFY_CATEGORY_NAME = 'ToontownAIRepository'
UD_NOITFY_CATEGORY_NAME = 'ToontownUberRepository'

ASTRON_EXCEPTION_MSG = ':%s(warning): INTERNAL-EXCEPTION: '
PYTHON_TRACEBACK_MSG = 'Traceback (most recent call last):'

ASTRON_DONE_MSG = 'Event Logger: Opened new log.'
UD_DONE_MSG = f':{UD_NOITFY_CATEGORY_NAME}: Done.'
AI_DONE_MSG = f':{AI_NOITFY_CATEGORY_NAME}: District is now ready. Have fun in Toontown Ranked!'


class DedicatedServer:
    notify = DirectNotifyGlobal.directNotify.newCategory('DedicatedServer')

    def __init__(self, localServer=False):
        self.notify.info('Starting DedicatedServer.')
        self.localServer = localServer

        self.astronProcess = None
        self.uberDogProcess = None
        self.aiProcess = None

        self.astronLog = None
        self.uberDogLog = None
        self.aiLog = None

        self.uberDogInternalExceptions = []
        self.aiInternalExceptions = []

        self.notify.setInfo(True)

    def start(self):
        # Register self.killProcesses with atexit in the event of a hard exit,
        # so that the server processes are killed if they're running.
        atexit.register(self.killProcesses)

        if self.localServer:
            self.notify.info('Starting local server...')
        else:
            self.notify.info('Starting dedicated server...')

        if ConfigVariableBool('local-multiplayer', True).getValue() and not self.localServer:
            self.notify.error("You are trying to start the server manually, but local-multiplayer is enabled!\n"
                              "You do not need to run this file in singleplayer mode, the server will automatically start on bootup.")

        taskMgr.add(self.startAstron, 'startAstron')

    def openAstronProcess(self, astronConfig):
        if sys.platform == 'win32':
            self.astronProcess = subprocess.Popen('astron/astrond.exe --loglevel info %s' % astronConfig,
                                                  stdin=self.astronLog, stdout=self.astronLog, stderr=self.astronLog)
        elif sys.platform == 'darwin':
            self.astronProcess = subprocess.Popen('astron/astrondmac --loglevel info %s' % astronConfig,
                                                  stdin=self.astronLog, stdout=self.astronLog, stderr=self.astronLog, shell=True)
        elif sys.platform == 'linux':
            self.astronProcess = subprocess.Popen('astron/astrondlinux --loglevel info %s' % astronConfig,
                                                  stdin=self.astronLog, stdout=self.astronLog, stderr=self.astronLog)
        else:
            self.notify.error(f"The following platform is not supported: {sys.platform}")

    def startAstron(self, task):
        self.notify.info('Starting Astron...')

        # Create and open the log file to use for Astron.
        astronLogFile = self.generateLog('astron')
        self.astronLog = open(astronLogFile, 'a')
        self.notify.info('Opened new Astron log: %s' % astronLogFile)

        # Use the Astron config file based on the database.
        astronConfig = ConfigVariableString('astron-config-path', 'astron/config/astrond.yml').getValue()

        # Start Astron process.
        self.openAstronProcess(astronConfig)
        # Setup a Task to start the UberDOG process when Astron is done.
        taskMgr.add(self.startUberDog, 'startUberDog')

    def startUberDog(self, task):
        # Check if Astron is ready through the log.
        astronLogFile = self.astronLog.name
        astronLog = open(astronLogFile)
        astronLogData = astronLog.read()
        astronLog.close()
        if ASTRON_DONE_MSG not in astronLogData:
            # Astron has not started yet. Rerun the task.
            return task.again

        # Astron has started
        self.notify.info('Astron started successfully!')

        ''' UberDOG '''
        self.notify.info('Starting UberDOG server...')

        # Create and open the log file to use for UberDOG.
        uberDogLogFile = self.generateLog('uberdog')
        self.uberDogLog = open(uberDogLogFile, 'a')
        self.notify.info('Opened new UberDOG log: %s' % uberDogLogFile)

        # Setup UberDOG arguments.
        if "__compile__" not in globals():
            if sys.platform == 'win32':
                uberDogArguments = '%s -m toontown.uberdog.UDStart' % open('launch/windows/PPYTHON_PATH').read()
            else:
                uberDogArguments = 'python3 -m toontown.uberdog.UDStart'

        else:
            if sys.platform == 'win32':
                uberDogArguments = 'RankedEngine.exe --uberdog'
            else:
                uberDogArguments = 'RankedEngine --uberdog'

        if ConfigVariableBool('local-multiplayer', True).getValue():
            gameServicesDialog['text'] = OTPLocalizer.CRLoadingGameServices + '\n\n' + OTPLocalizer.CRLoadingGameServicesUberdog

        # Start UberDOG process.
        if sys.platform in ['win32', 'linux']:
            self.uberDogProcess = subprocess.Popen(uberDogArguments, stdin=self.uberDogLog, stdout=self.uberDogLog, stderr=self.uberDogLog)
        elif sys.platform == 'darwin':
            self.uberDogProcess = subprocess.Popen(uberDogArguments, stdin=self.uberDogLog, stdout=self.uberDogLog, stderr=self.uberDogLog, shell=True)
        # Start the AI process when UberDOG is done.
        taskMgr.add(self.startAI, 'startAI')

        # Once started, we can end this task.
        return task.done

    def startAI(self, task):
        # Check if UberDOG is ready through the log.
        uberDogLogFile = self.uberDogLog.name
        uberDogLog = open(uberDogLogFile)
        uberDogLogData = uberDogLog.read()
        uberDogLog.close()
        if UD_DONE_MSG not in uberDogLogData:
            # UberDOG has not started yet. Rerun the task.
            return task.again

        # UberDOG has started
        self.notify.info('UberDOG started successfully!')

        ''' AI '''
        self.notify.info('Starting AI server...')

        # Create and open the log file to use for AI.
        aiLogFile = self.generateLog('ai')
        self.aiLog = open(aiLogFile, 'a')
        self.notify.info('Opened new AI log: %s' % aiLogFile)

        # Setup AI arguments.
        if "__compile__" not in globals():
            if sys.platform == 'win32':
                aiArguments = '%s -m toontown.ai.AIStart' % open('launch/windows/PPYTHON_PATH').read()
            else:
                aiArguments = 'python3 -m toontown.ai.AIStart'
        else:
            if sys.platform == 'win32':
                aiArguments = 'RankedEngine.exe --ai'
            else:
                aiArguments = 'RankedEngine --ai'

        if ConfigVariableBool('local-multiplayer', True).getValue():
            gameServicesDialog['text'] = OTPLocalizer.CRLoadingGameServices + '\n\n' + OTPLocalizer.CRLoadingGameServicesAI

        # Start AI process.
        if sys.platform in ['win32', 'linux']:
            self.aiProcess = subprocess.Popen(aiArguments, stdin=self.aiLog, stdout=self.aiLog, stderr=self.aiLog)
        elif sys.platform == 'darwin':
            self.aiProcess = subprocess.Popen(aiArguments, stdin=self.aiLog, stdout=self.aiLog, stderr=self.aiLog, shell=True)
        # Send a message to note the server has started.
        taskMgr.add(self.serverStarted, 'serverStarted')

        # Once started, we can end this task.
        return task.done

    def serverStarted(self, task):
        # Check if the AI is ready through the log.
        aiLogFile = self.aiLog.name
        aiLog = open(aiLogFile)
        aiLogData = aiLog.read()
        aiLog.close()
        if AI_DONE_MSG not in aiLogData:
            # AI has not started yet. Rerun the task.
            return task.again

        # AI has started
        self.notify.info('AI started successfully!')

        # Every aspect of the server has started. Let's finish with the done message.
        self.notify.info('Server now ready. Have fun in Toontown Ranked!')
        if self.localServer:
            messenger.send('localServerReady')

        # Setup a Task to check if the server has crashed.
        taskMgr.add(self.checkForCrashes, 'checkForCrashes')

        # Otherwise, we can end this task.
        return task.done

    def checkForCrashes(self, task):
        # Check if the AI server has crashed.
        aiLogFile = self.aiLog.name
        aiLog = open(aiLogFile)
        aiLogData = aiLog.readlines()
        aiLog.close()
        astronException = ASTRON_EXCEPTION_MSG % AI_NOITFY_CATEGORY_NAME
        for line in aiLogData:
            if PYTHON_TRACEBACK_MSG or astronException in line:
                if PYTHON_TRACEBACK_MSG in line:
                    # The AI server has crashed!
                    self.killProcesses()
                    self.notify.error("The AI server has crashed, you will need to restart your server."
                                      "\n\nIf this problem persists, please report the bug and provide "
                                      "them with your most recent log from the \"logs/ai\" folder.")
                elif astronException in line:
                    if line not in self.aiInternalExceptions:
                        self.aiInternalExceptions.append(line)
                        self.notify.warning(f'An internal exception has occurred in the AI server: {line}')

        # Check if the UberDOG server has crashed.
        uberDogLogFile = self.uberDogLog.name
        uberDogLog = open(uberDogLogFile)
        uberDogLogData = uberDogLog.readlines()
        uberDogLog.close()
        astronException = ASTRON_EXCEPTION_MSG % UD_NOITFY_CATEGORY_NAME
        for line in uberDogLogData:
            if PYTHON_TRACEBACK_MSG or astronException in line:
                if PYTHON_TRACEBACK_MSG in line:
                    # The UberDOG server has crashed!
                    self.killProcesses()
                    self.notify.error("The UberDOG server has crashed, you will need to restart your server."
                                      "\n\nIf this problem persists, please report the bug and provide "
                                      "them with your most recent log from the \"logs/uberdog\" folder.")
                elif astronException in line:
                    if line not in self.uberDogInternalExceptions:
                        self.uberDogInternalExceptions.append(line)
                        self.notify.warning(f'An internal exception has occurred in the UberDOG server: {line}')

        # Keep running this Task if the server has not crashed.
        return task.again

    def killProcesses(self):
        # Terminate server processes in reverse order of how they were started, starting with the AI.
        if self.aiProcess:
            self.aiProcess.terminate()

        # Next is UberDOG.
        if self.uberDogProcess:
            self.uberDogProcess.terminate()

        # And lastly, Astron.
        if self.astronProcess:
            self.astronProcess.terminate()

    @staticmethod
    def generateLog(logPrefix):
        ltime = 1 and time.localtime()
        logSuffix = '%02d%02d%02d_%02d%02d%02d' % (ltime[0] - 2000, ltime[1], ltime[2],
                                                   ltime[3], ltime[4], ltime[5])

        if not os.path.exists('logs/'):
            os.mkdir('logs/')

        if not os.path.exists('logs/%s/' % logPrefix):
            os.mkdir('logs/%s/' % logPrefix)

        logFile = 'logs/%s/%s-%s.log' % (logPrefix, logPrefix, logSuffix)

        return logFile
