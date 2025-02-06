from toontown.dna import DNANode, DNAUtil
from panda3d.core import DecalEffect

class DNASignText(DNANode.DNANode):
    __slots__ = ('letters', 'code', 'color')
    
    COMPONENT_CODE = 7

    def __init__(self, name):
        DNANode.DNANode.__init__(self, name)
        self.letters = ''

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

    def traverse(self, nodePath, store):
        parentNode = nodePath
        while parentNode.node().isGeomNode():
            parentNode = parentNode.getParent()

        parentNode.setEffect(DecalEffect.make())