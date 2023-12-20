#!/usr/bin/env python3

import sys

from CommandUtils import CommandUtils

cmdUtils = CommandUtils()


def cleanUpChroot(chrootPath):
    returnVal, listmountpoints = findmountpoints(chrootPath)

    if not returnVal:
        return False

    sortmountpoints(listmountpoints)

    print(listmountpoints)

    if not unmountmountpoints(listmountpoints):
        return False

    return bool(removeAllFilesFromChroot(chrootPath))


def removeAllFilesFromChroot(chrootPath):
    cmd = f"rm -rf {chrootPath}"
    _, _, rc = cmdUtils.runBashCmd(cmd, capture=True, ignore_rc=True)
    if rc:
        print(f"Unable to remove files from chroot {chrootPath}")
        return False
    return True


def unmountmountpoints(listmountpoints):
    if listmountpoints is None:
        return True
    result = True
    for mountpoint in listmountpoints:
        cmd = f"umount {mountpoint}"
        _, _, rc = cmdUtils.runBashCmd(cmd, capture=True, ignore_rc=True)
        if rc:
            result = False
            print(f"Unable to unmount {mountpoint}")
            break
    if not result:
        print("Unable to unmount all mounts. Unable to clean up the chroot")
        return False
    return True


def findmountpoints(chrootPath):
    if not chrootPath.endswith("/"):
        chrootPath = f"{chrootPath}/"
    cmd = f"mount | grep {chrootPath} | cut -d' ' -s -f3"
    mountpoints, _, rc = cmdUtils.runBashCmd(cmd, capture=True, ignore_rc=True)
    if rc:
        print("Unable to find mountpoints in chroot")
        return False, None

    mountpoints = mountpoints.replace("\n", " ").strip()
    if mountpoints == "":
        print("No mount points found")
        return True, None

    listmountpoints = mountpoints.split(" ")
    return True, listmountpoints


def sortmountpoints(listmountpoints):
    if listmountpoints is None:
        return True
    sortedmountpoints = listmountpoints
    sorted(sortedmountpoints)
    sortedmountpoints.reverse()


def main():
    if len(sys.argv) < 2:
        print("Usage: ./clean-up-chroot.py <chrootpath>")
        sys.exit(1)
    if not cleanUpChroot(sys.argv[1]):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
