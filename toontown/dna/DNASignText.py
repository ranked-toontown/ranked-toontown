from toontown.dna import DNAStorage, DNANode, DNAUtil, DNASignBaseline, DNAError, DNAGroup
from panda3d.core import DecalEffect, TextNode, LVecBase3f, LVecBase4f, TextEncoder, LVector3

class DNASignText(DNANode.DNANode):
    __slots__ = ('letters', 'code', 'color', 'useBaselineColor')
    
    COMPONENT_CODE = 7

    def __init__(self, name):
        DNANode.DNANode.__init__(self, name)
        self.code = None
        self.letters = ''
        self.color = LVecBase4f(0)
        self.useBaselineColor = True

    def __del__(self):
        DNANode.DNANode.__del__(self)
        del self.letters
        del self.code
        del self.color

    def makeFromDGI(self, dgi, store):
        DNANode.DNANode.makeFromDGI(self, dgi, store)
        self.letters = dgi.getString()
        self.code = dgi.getString()
        self.color = DNAUtil.dgiExtractColor(dgi)

    def traverse(self, nodePath, store: DNAStorage.DNAStorage):
        geomParent = nodePath
        node = geomParent.node()
        while not node.isGeomNode() and not geomParent.isSingleton():
            geomParent = geomParent.getParent()
            node = geomParent.node()
        if node.isGeomNode():
            node.setEffect(DecalEffect.make())
        
        baseline = self.parent
        if isinstance(baseline, DNASignBaseline.DNASignBaseline):
            code = baseline.code

            font = store.findFont(code)
            if not font:
                raise DNAError.DNAError('Could not find font in dnaStore.')
                
            if self.useBaselineColor:
                color = baseline.color

            textNode = TextNode("sign")
            textNode.setTextColor(color)
            textNode.setFont(font)

            if "c" in baseline.flags:
                encoder = TextEncoder()
                encoder.setText(self.letters)
                numChars = encoder.getNumChars()
                for i in range(numChars):
                    character = encoder.getUnicodeChar(i)
                    encoder.setUnicodeChar(i, encoder.unicodeToupper(character))

            if "d" in baseline.flags:
                textNode.setShadowColor(self.color[0] * 0.3, self.color[1] * 0.3, self.color[2] * 0.3, self.color[3] * 0.7)
                textNode.setShadow(0.03, 0.03)
            textNode.setText(self.letters)

            blPos = self.pos
            blHpr = self.hpr
            blScale = self.scale
            if "b" in baseline.flags and baseline.isFirstLetterOfWord(self.letters):
                blScale[0] *= 1.5
                blScale[2] *= 1.5

            frame = LVecBase3f(textNode.getWidth(), 0, textNode.getHeight())
            pos, hpr, scale = baseline.baselineNextPosHprScale(blPos, blHpr, blScale, frame)

            signTextNodePath = nodePath.attachNewNode(textNode.generate())
            signTextNodePath.setPosHprScale(nodePath, pos, hpr, scale)
            signTextNodePath.setColorOff()
            signTextNodePath.setColor(self.color)

            self.traverseChildren(signTextNodePath, store)
        else:
            raise DNAError.DNAError('Baseline is not a DNASignBaseline object.')
