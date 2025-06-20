import os

from panda3d.core import VirtualFileSystem, ConfigVariableList, Filename


if __debug__:
    from panda3d.core import loadPrcFile
    loadPrcFile('config/common.prc')
    loadPrcFile('config/development.prc')
    loadPrcFile('config/production.prc')
else:
    import sys
    sys.path = ['']

if "__compiled__" not in globals():
    # The VirtualFileSystem, which has already initialized, doesn't see the mount
    # directives in the config(s) yet. We have to force it to load those manually:
    vfs = VirtualFileSystem.getGlobalPtr()
    mounts = ConfigVariableList('vfs-mount')
    for mount in mounts:
        mountFile, mountPoint = (mount.split(' ', 2) + [None, None, None])[:2]
        vfs.mount(Filename(mountFile), Filename(mountPoint), 0)

from toontown.launcher.TTOffQuickLauncher import TTOffQuickLauncher
launcher = TTOffQuickLauncher()
launcher.notify.info('Reached end of StartTTOffQuickLauncher.py.')
