from direct.controls.ControlManager import ControlManager
from direct.directnotify import DirectNotifyGlobal
from direct.showbase.InputStateGlobal import inputState


class ToontownControlManager(ControlManager):
    notify = DirectNotifyGlobal.directNotify.newCategory("TTControlManager")

    def __init__(self, enable=True):
        self.forceTokens = None
        self.craneControlsEnabled = False
        super().__init__(enable)

    def enable(self):
        assert self.notify.debugCall(id(self))

        if self.isEnabled:
            assert self.notify.debug('already isEnabled')
            return

        self.isEnabled = 1

        self.enableControls()

        # keep track of what we do on the inputState so we can undo it later on
        # self.inputStateTokens = []

        controls = base.controls
        up = controls.MOVE_UP
        down = controls.MOVE_DOWN
        left = controls.MOVE_LEFT
        right = controls.MOVE_RIGHT
        jump = controls.JUMP

        # Check if user already has arrow keys configured to avoid duplicates
        user_has_arrow_up = (up == "arrow_up")
        user_has_arrow_down = (down == "arrow_down")
        user_has_arrow_left = (left == "arrow_left")
        user_has_arrow_right = (right == "arrow_right")

        self.inputStateTokens.extend((
            inputState.watch("run", 'runningEvent', "running-on", "running-off"),

            # User-configured movement keys
            inputState.watchWithModifiers("forward", up, inputSource=inputState.ArrowKeys),
            inputState.watch("forward", "force-forward", "force-forward-stop"),

            inputState.watchWithModifiers("reverse", down, inputSource=inputState.ArrowKeys),
            inputState.watchWithModifiers("reverse", "mouse4", inputSource=inputState.Mouse),

            inputState.watchWithModifiers("turnLeft", left, inputSource=inputState.ArrowKeys),
            inputState.watch("turnLeft", "mouse-look_left", "mouse-look_left-done"),
            inputState.watch("turnLeft", "force-turnLeft", "force-turnLeft-stop"),

            inputState.watchWithModifiers("turnRight", right, inputSource=inputState.ArrowKeys),
            inputState.watch("turnRight", "mouse-look_right", "mouse-look_right-done"),
            inputState.watch("turnRight", "force-turnRight", "force-turnRight-stop"),

            inputState.watchWithModifiers("jump", jump),
        ))

        # Add default arrow key bindings (only if user doesn't already have them configured)
        if not user_has_arrow_up:
            self.inputStateTokens.append(
                inputState.watchWithModifiers("forward", "arrow_up", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_down:
            self.inputStateTokens.append(
                inputState.watchWithModifiers("reverse", "arrow_down", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_left:
            self.inputStateTokens.append(
                inputState.watchWithModifiers("turnLeft", "arrow_left", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_right:
            self.inputStateTokens.append(
                inputState.watchWithModifiers("turnRight", "arrow_right", inputSource=inputState.ArrowKeys)
            )

        self.setTurn(1)

        if self.currentControls:
            self.currentControls.enableAvatarControls()

    def enableControls(self):
        if self.forceTokens:
            for token in self.forceTokens:
                token.release()
            self.forceTokens = []

    def disableControls(self):
        self.forceTokens = [
            inputState.force('jump', 0, 'TTControlManager.disableControls'),
            inputState.force('forward', 0, 'TTControlManager.disableControls'),
            inputState.force('turnLeft', 0, 'TTControlManager.disableControls'),
            inputState.force('slideLeft', 0, 'TTControlManager.disableControls'),
            inputState.force('reverse', 0, 'TTControlManager.disableControls'),
            inputState.force('turnRight', 0, 'TTControlManager.disableControls'),
            inputState.force('slideRight', 0, 'TTControlManager.disableControls')
        ]

    def setTurn(self, turn):
        self.__WASDTurn = turn

        if not self.isEnabled:
            return

        turnLeftWASDSet = inputState.isSet("turnLeft", inputSource=inputState.ArrowKeys)
        turnRightWASDSet = inputState.isSet("turnRight", inputSource=inputState.ArrowKeys)
        slideLeftWASDSet = inputState.isSet("slideLeft", inputSource=inputState.ArrowKeys)
        slideRightWASDSet = inputState.isSet("slideRight", inputSource=inputState.ArrowKeys)

        for token in self.WASDTurnTokens:
            token.release()

        controls = base.controls
        left = controls.MOVE_LEFT
        right = controls.MOVE_RIGHT

        # Check if user already has arrow keys configured to avoid duplicates
        user_has_arrow_left = (left == "arrow_left")
        user_has_arrow_right = (right == "arrow_right")

        if turn:
            turn_tokens = [
                inputState.watchWithModifiers("turnLeft", left, inputSource=inputState.ArrowKeys),
                inputState.watchWithModifiers("turnRight", right, inputSource=inputState.ArrowKeys),
            ]
            
            # Add default arrow key bindings for turn mode (only if user doesn't already have them)
            if not user_has_arrow_left:
                turn_tokens.append(
                    inputState.watchWithModifiers("turnLeft", "arrow_left", inputSource=inputState.ArrowKeys)
                )
            if not user_has_arrow_right:
                turn_tokens.append(
                    inputState.watchWithModifiers("turnRight", "arrow_right", inputSource=inputState.ArrowKeys)
                )
            
            self.WASDTurnTokens = tuple(turn_tokens)

            inputState.set("turnLeft", slideLeftWASDSet, inputSource=inputState.ArrowKeys)
            inputState.set("turnRight", slideRightWASDSet, inputSource=inputState.ArrowKeys)

            inputState.set("slideLeft", False, inputSource=inputState.ArrowKeys)
            inputState.set("slideRight", False, inputSource=inputState.ArrowKeys)

        else:
            slide_tokens = [
                inputState.watchWithModifiers("slideLeft", left, inputSource=inputState.ArrowKeys),
                inputState.watchWithModifiers("slideRight", right, inputSource=inputState.ArrowKeys),
            ]
            
            # Add default arrow key bindings for slide mode (only if user doesn't already have them)
            if not user_has_arrow_left:
                slide_tokens.append(
                    inputState.watchWithModifiers("slideLeft", "arrow_left", inputSource=inputState.ArrowKeys)
                )
            if not user_has_arrow_right:
                slide_tokens.append(
                    inputState.watchWithModifiers("slideRight", "arrow_right", inputSource=inputState.ArrowKeys)
                )
            
            self.WASDTurnTokens = tuple(slide_tokens)

            inputState.set("slideLeft", turnLeftWASDSet, inputSource=inputState.ArrowKeys)
            inputState.set("slideRight", turnRightWASDSet, inputSource=inputState.ArrowKeys)

            inputState.set("turnLeft", False, inputSource=inputState.ArrowKeys)
            inputState.set("turnRight", False, inputSource=inputState.ArrowKeys)

    def enableCraneControls(self):
        """
        This function should only be called for when our controls are disabled,
        but we need to map our movement keys to functions. (i.e. on a crane, on a banquet table, etc.)
        This serves as an improved implementation of 'passMessagesThrough'.
        """

        if self.isEnabled and self.craneControlsEnabled:
            return

        controls = base.controls

        # Check if user already has arrow keys configured to avoid duplicates
        user_has_arrow_up = (controls.MOVE_UP == "arrow_up")
        user_has_arrow_down = (controls.MOVE_DOWN == "arrow_down")
        user_has_arrow_left = (controls.MOVE_LEFT == "arrow_left")
        user_has_arrow_right = (controls.MOVE_RIGHT == "arrow_right")

        crane_tokens = [
            # User-configured movement keys
            inputState.watchWithModifiers("forward", controls.MOVE_UP, inputSource=inputState.ArrowKeys),
            inputState.watchWithModifiers("reverse", controls.MOVE_DOWN, inputSource=inputState.ArrowKeys),
            inputState.watchWithModifiers("turnLeft", controls.MOVE_LEFT, inputSource=inputState.ArrowKeys),
            inputState.watchWithModifiers("turnRight", controls.MOVE_RIGHT, inputSource=inputState.ArrowKeys),
        ]
        
        # Add default arrow key bindings (only if user doesn't already have them configured)
        if not user_has_arrow_up:
            crane_tokens.append(
                inputState.watchWithModifiers("forward", "arrow_up", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_down:
            crane_tokens.append(
                inputState.watchWithModifiers("reverse", "arrow_down", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_left:
            crane_tokens.append(
                inputState.watchWithModifiers("turnLeft", "arrow_left", inputSource=inputState.ArrowKeys)
            )
        if not user_has_arrow_right:
            crane_tokens.append(
                inputState.watchWithModifiers("turnRight", "arrow_right", inputSource=inputState.ArrowKeys)
            )

        self.inputStateTokens.extend(crane_tokens)

    def disableCraneControls(self):
        """
        Disables crane controls.
        """

        if not self.isEnabled and not self.craneControlsEnabled:
            return

        for token in self.inputStateTokens:
            token.release()
        self.inputStateTokens = []
