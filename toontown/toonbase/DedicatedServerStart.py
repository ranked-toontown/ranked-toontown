from panda3d.core import loadPrcFile, VirtualFileSystem, Filename, ConfigVariableList, loadPrcFileData
from direct.showbase.ShowBase import ShowBase
from toontown.toonbase.DedicatedServer import DedicatedServer

if "__compiled__" not in globals():
    loadPrcFile('config/common.prc')
    loadPrcFile('config/development.prc')

    # The VirtualFileSystem, which has already initialized, doesn't see the mount
    # directives in the config(s) yet. We have to force it to load those manually:
    vfs = VirtualFileSystem.getGlobalPtr()
    mounts = ConfigVariableList('vfs-mount')
    for mount in mounts:
        mountFile, mountPoint = (mount.split(' ', 2) + [None, None, None])[:2]
        vfs.mount(Filename(mountFile), Filename(mountPoint), 0)

loadPrcFileData('window config', 'window-type none')

ShowBase()
dedicatedServer = DedicatedServer(localServer=False)
dedicatedServer.start()
base.run()
