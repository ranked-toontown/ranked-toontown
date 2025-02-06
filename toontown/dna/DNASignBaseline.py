import math
from panda3d.core import NodePath, TextNode, DecalEffect, LVecBase3f
from toontown.dna import DNANode, DNAUtil, DNAError

class DNASignBaseline(DNANode.DNANode):
    COMPONENT_CODE = 6

    def __init__(self, name):
        DNANode.DNANode.__init__(self, name)
        self.currPos = LVecBase3f(0)
        self.field252 = 0
        self.angle = 0
        self.isSpace = False
        self.counter = 0
        self.wasSpace = False

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
        _np = nodePath.attachNewNode("baseline")

        if self.code:
            font = dnaStorage.findFont(self.code)
            if font == None:
                raise DNAError.DNAError(f'Font code {self.code} not found.')

        self.traverseChildren(_np, dnaStorage)

        newPos, newHpr = self.center(self.pos, self.hpr)
        _np.setPosHpr(newPos, newHpr)

    def center(self, pos, hpr):
        angle = -hpr[2] * math.pi / 180
        newPos = LVecBase3f()
        newHpr = LVecBase3f()
        if self.width and self.height != 0:
            newPos[0] = pos[0] - math.cos(angle + math.pi / 2) * self.width * 0.5
            newPos[2] = pos[2] - math.sin(angle + math.pi / 2) * self.height * 0.5
            newHpr[2] = hpr[2] + self.field252 * 0.5
        else:
            self.counter -= 1
            stumble = self.stumble * (1 if (self.counter & 1) else -1)
            scale = (stumble + self.counter * self.kern + self.currPos[0]) * 0.5
            newPos[0] = pos[0] - math.cos(angle) * scale
            newPos[2] = pos[2] - math.sin(angle) * scale
            self.counter += 1
        
        newPos[1] = -0.05
        return newPos, newHpr

    def lineNextPosHrpScale(self, pos, hpr, scale, frame):
        newPos = LVecBase3f()
        newHpr = LVecBase3f()
        newScale = LVecBase3f()

        newPos[0] = self.currPos[0] = self.counter * self.kern + self.stumble * (1 if (self.counter & 1) else -1)
        newPos[1] = self.currPos[1]
        newPos[2] = self.currPos[2] + self.stomp * (1 if (self.counter & 1) else -1)

        newScale[0] = scale[0] * self.scale[0]
        newScale[1] = scale[1] * self.scale[1]
        newScale[2] = scale[2] * self.scale[2]

        newHpr[2] = hpr[2] - (1 if (self.counter & 1) else -1)

        self.currPos[0] += newScale[0] * frame[0]
        self.counter += 1

        return newPos, newHpr, newScale, frame

    def circleNextPosHprScale(self, pos, hpr, scale, frame):
        newPos = LVecBase3f()
        newHpr = LVecBase3f()
        newScale = LVecBase3f()

        newScale[0] = scale[0] * self.scale[0]
        newScale[1] = scale[1] * self.scale[1]
        newScale[2] = scale[2] * self.scale[2]

        v39 = self.width * 0.5
        v43 = self.height * 0.5

        v11 = pos[0] if self.width == 0 else -pos[0]
        v14 = v11 / v39

        v38 = self.indent if self.width == 0 else -self.indent
        xPosition = self.angle * math.pi / 180
        v40 = v38 * math.pi / 180 + v14 + xPosition + math.pi / 2

        xScale = self.stomp * (1 if (self.counter & 1) else -1) + pos[2]
        if self.width < 0:
            xScale *= -1

        v39 = (xScale + v39) * math.cos(v40)
        v22 = xScale + v43

        newPos[0] = v39
        yScale = v22 * math.sin(v40)
        newPos[2] = yScale

        v26 = self.wiggle * (1 if (self.counter & 1) else -1)
        newHpr[2] = hpr[2] - (v26 + self.angle + v38)

        zScale = math.sqrt(yScale * yScale + math.pow(v39, 2))
        if self.width < 0:
            self.field252 = xPosition * 180 / math.pi

        heading = min(1, scale[0] * frame[0] / (zScale * 2))
        yPosition = xPosition - 2 * math.asin(heading)

        if self.width >= 0:
            self.field252 = yPosition * 180 / math.pi

        pitch = self.stumble * (1 if (self.counter & 1) else -1)

        arcSine = math.asin((self.kern - pitch) / (zScale * 2))
        self.angle = (yPosition - (arcSine * 2)) * 180 / math.pi

        if self.width >= 0:
            newHpr[2] = hpr[2] + (self.angle * 2) * 0.5

        self.counter += 1

        return newPos, newHpr, newScale, frame

    def baselineNextPosHprScale(self, pos, hpr, scale, frame):
        if self.width and self.height != 0:
            self.circleNextPosHprScale(pos, hpr, scale, frame)
        else:
            self.lineNextPosHrpScale(pos, hpr, scale, frame)

    def isFirstLetterOfWord(self, char):
        if char == ' ':
            self.isSpace = True
            return False
        else:
            self.wasSpace = self.isSpace
            self.isSpace = False
            return self.wasSpace