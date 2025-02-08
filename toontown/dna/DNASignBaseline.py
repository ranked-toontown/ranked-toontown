import math
from panda3d.core import NodePath, TextNode, DecalEffect, LVecBase3f, LVecBase4f
from toontown.dna import DNANode, DNAUtil, DNAError

class DNASignBaseline(DNANode.DNANode):
    COMPONENT_CODE = 6

    def __init__(self, name):
        DNANode.DNANode.__init__(self, name)
        self.color = LVecBase4f(1)
        self.indent = 0
        self.kern = 0
        self.wiggle = 0
        self.stumble = 0
        self.stomp = 0
        self.width = 0
        self.height = 0
        self.currPos = LVecBase3f(0)
        self.oldCursor = 0
        self.cursor = 0
        self.isSpace = False
        self.counter = 0
        self.wasSpace = False
        self.totalWidth = 0
        self.nextPos = LVecBase3f(0)

    def __del__(self):
        DNANode.DNANode.__del__(self)

        if not hasattr(self, 'text'):
            return

        del self.code
        del self.color
        del self.flags
        del self.indent
        del self.kern
        del self.wiggle
        del self.stumble
        del self.stomp
        del self.width
        del self.height
        del self.currPos
        del self.oldCursor
        del self.cursor
        del self.isSpace
        del self.counter
        del self.wasSpace
        del self.totalWidth
        del self.nextPos

    def makeFromDGI(self, dgi, store):
        DNANode.DNANode.makeFromDGI(self, dgi, store)
        self.code = dgi.getString()
        self.color = DNAUtil.dgiExtractColor(dgi)
        self.flags = dgi.getString()
        self.indent = dgi.getFloat32()
        self.kern = dgi.getFloat32()
        self.wiggle = dgi.getFloat32()
        self.stumble = dgi.getFloat32()
        self.stomp = dgi.getFloat32()
        self.width = dgi.getFloat32()
        self.height = dgi.getFloat32()

    def traverse(self, nodePath, dnaStorage):
        self.reset()

        _np = nodePath.attachNewNode("baseline")

        if self.code:
            font = dnaStorage.findFont(self.code)
            if font == None:
                raise DNAError.DNAError(f'Font code {self.code} not found.')

        self.traverseChildren(_np, dnaStorage)

        newPos, newHpr = self.center(self.pos, self.hpr)
        _np.setDepthWrite(0)
        _np.setPosHpr(newPos, newHpr)

    def center(self, pos, hpr):
        pi = math.pi
        quarterCircle = pi * 0.5
        degreesToRadians = pi / 180.0

        angle = -self.hpr[2] * degreesToRadians
        newPos = LVecBase3f(0)
        newHpr = LVecBase3f(0)
        if self.width and self.height != 0:
            xRadius = self.width * 0.5
            zRadius = self.height * 0.5

            angle += quarterCircle

            cosAngle = math.cos(angle)
            sinAngle = math.sin(angle)

            newPos[0] = pos[0] - xRadius * cosAngle
            newPos[2] = pos[2] - zRadius * sinAngle

            newHpr[2] = hpr[2] + self.oldCursor * 0.5
        else:
            self.counter -= 1
            gapWidth = self.kern + self.stumble
            self.counter += 1
            radius = (self.totalWidth + gapWidth) * 0.5

            cosAngle = math.cos(angle)
            sinAngle = math.sin(angle)

            newPos[0] = pos[0] - radius * cosAngle
            newPos[2] = pos[2] - radius * sinAngle
        
        newPos[1] = -0.05

        return newPos, newHpr

    def lineNextPosHrpScale(self, pos, hpr, scale, frame):
        newPos = LVecBase3f(0)
        newHpr = LVecBase3f(0)
        newScale = LVecBase3f(0)

        newScale[0] = scale[0] * self.scale[0]
        newScale[1] = scale[1] * self.scale[1]
        newScale[2] = scale[2] * self.scale[2]

        newPos = pos + self.nextPos
        newPos[0] = newPos[0] + self.kern + self.stumble
        newPos[2] = newPos[2] + self.stomp

        scaledWidth = newScale[0] * frame[0]
        self.nextPos[0] += scaledWidth
        self.totalWidth += scaledWidth
        newHpr[2] = hpr[2] - self.wiggle
        self.counter += 1

        return newPos, newHpr, newScale

    def circleNextPosHprScale(self, pos, hpr, scale, frame):
        newPos = LVecBase3f(0)
        newHpr = LVecBase3f(0)
        newScale = LVecBase3f(0)

        pi = math.pi
        quarterCircle = pi * 0.5
        degreesToRadians = pi / 180.0
        radiansToDegrees = 180.0 / pi

        newScale[0] = scale[0] * self.scale[0]
        newScale[1] = scale[1] * self.scale[1]
        newScale[2] = scale[2] * self.scale[2]

        xRadius = self.width * 0.5
        zRadius = self.height * 0.5

        xOffset = pos[0] if self.width < 0.0 else -pos[0]
        halfCircle = pi * xRadius
        radianWidthDelta = xOffset / halfCircle * pi

        degreeDelta = -self.indent if self.width < 0.0 else self.indent
        radianDelta = degreeDelta * degreesToRadians + radianWidthDelta
        radianCursor = self.cursor * degreesToRadians
        radianTotal = radianCursor + quarterCircle + radianDelta

        radiusDelta = pos[2] + self.stomp
        if self.width < 0:
            radiusDelta = -radiusDelta

        cosAngle = math.cos(radianTotal)
        sinAngle = math.sin(radianTotal)

        newX = (xRadius + radiusDelta) * cosAngle
        newZ = (zRadius + radiusDelta) * sinAngle

        newPos[0] = newX
        newPos[2] = newZ

        newHpr[2] = hpr[2] - self.cursor + degreeDelta + self.wiggle

        hypot = math.sqrt(newX * newX + newZ * newZ)

        if self.width < 0:
            self.oldCursor = radianCursor * radiansToDegrees
        scaledWidth = newScale[0] * frame[0]
        radianCursor = radianCursor - 2.0 * math.asin(min(scaledWidth / (2.0 * hypot), 1.0))
        if self.width >= 0:
            self.oldCursor = radianCursor * radiansToDegrees
        
        gapWidth = self.kern - self.stumble
        radianCursor = radianCursor - 2.0 * math.asin(gapWidth / (2.0 * hypot))
        tempCursor = self.cursor
        self.cursor = radianCursor * radiansToDegrees

        knockBack = (self.cursor - tempCursor) * 0.5
        if self.width >= 0:
            newHpr[2] = newHpr[2] - knockBack

        self.counter += 1

        return newPos, newHpr, newScale

    def baselineNextPosHprScale(self, pos, hpr, scale, frame):
        if self.width and self.height != 0:
            newPos, newHpr, newScale = self.circleNextPosHprScale(pos, hpr, scale, frame)
        else:
            newPos, newHpr, newScale = self.lineNextPosHrpScale(pos, hpr, scale, frame)
        return newPos, newHpr, newScale

    def isFirstLetterOfWord(self, char):
        if char == ' ':
            self.isSpace = True
            return False
        else:
            self.wasSpace = self.isSpace
            self.isSpace = False
            return self.wasSpace

    def reset(self):
        self.currPos = LVecBase3f(0)
        self.oldCursor = 0
        self.cursor = 0
        self.isSpace = True
        self.counter = 0
        self.totalWidth = 0
        self.nextPos = LVecBase3f(0)