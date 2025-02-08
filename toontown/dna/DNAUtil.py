from panda3d.core import LVecBase4f

def dgiExtractString8(dgi):
    return dgi.getString()

def dgiExtractColor(dgi):
    color = LVecBase4f()
    color[0] = dgi.get_uint8() / 255
    color[1] = dgi.get_uint8() / 255
    color[2] = dgi.get_uint8() / 255
    color[3] = dgi.get_uint8() / 255
    return color