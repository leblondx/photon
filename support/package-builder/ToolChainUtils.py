#!/usr/bin/env python3

import os.path
import re

from CommandUtils import CommandUtils
from Logger import Logger
from PackageUtils import PackageUtils
from constants import constants
from SpecData import SPECS
from StringUtils import StringUtils


class ToolChainUtils(object):
    def __init__(self, logName=None, logPath=None):
        if logName is None:
            logName = "Toolchain Utils"
        if logPath is None:
            logPath = constants.logPath

        self.cmdUtils = CommandUtils()
        self.logName = logName
        self.logPath = logPath
        self.logger = Logger.getLogger(logName, logPath, constants.logLevel)
        """
        self.rpmCommand is used for rpm installation of dependent packages
        inside the sandbox.
        There are 4 possible scenarios:
        1. EUID == 0 and rpm supports all needed features (usable)
           -> use "rpm -i ..."
        2. EUID == 0 and rpm is not usable
           -> use rpm from docker "docker ... -c rpm -i ..."
        3. EUID != 0 and host rpm is usable
           -> use "fakeroot-ng rpm -i ..."
        4. EUID != 0 and rpm is not usable
           -> use rpm from docker "docker ... -c rpm -i ..."
           -> run "chown -R EUID:EGID /" after to do not deal with root
        owned files.
        """
        if os.geteuid() == 0 or constants.hostRpmIsNotUsable:
            self.rpmCommand = "rpm"
        else:
            self.rpmCommand = "fakeroot-ng rpm"

    def _findPublishedRPM(self, package, rpmdirPath):
        listFoundRPMFiles = self.cmdUtils.findFile(
            f"{package}-*.rpm", rpmdirPath
        )
        listFilterRPMFiles = []
        for f in listFoundRPMFiles:
            rpmFileName = os.path.basename(f)
            checkRPMName = rpmFileName.replace(package, "")
            rpmNameSplit = checkRPMName.split("-")
            if len(rpmNameSplit) == 3:
                listFilterRPMFiles.append(f)
        if len(listFilterRPMFiles) == 1:
            return listFilterRPMFiles[0]
        if not listFilterRPMFiles:
            return None
        if len(listFilterRPMFiles) > 1:
            self.logger.error(
                "Found multiple rpm files for given package in rpm directory."
                + "Unable to determine the rpm file for package:"
                + package
            )
            return None

    def getListDependentPackages(self, package, version):
        listBuildRequiresPkg = SPECS.getData(
            constants.buildArch
        ).getBuildRequiresForPackage(package, version)
        listBuildRequiresPkg.extend(
            SPECS.getData(constants.buildArch).getCheckBuildRequiresForPackage(
                package, version
            )
        )
        return listBuildRequiresPkg

    def installToolchainRPMS(
        self,
        chroot,
        packageName=None,
        packageVersion=None,
        usePublishedRPMS=True,
        availablePackages=None,
    ):
        self.logger.debug("Installing toolchain RPMS.......")
        packages = ""
        listBuildRequiresPackages = []
        ChrootID = chroot.getID()

        listRPMsToInstall = list(constants.listToolChainRPMsToInstall)
        if constants.crossCompiling:
            targetPackageName = packageName
            packageName = None
            packageVersion = None
            listRPMsToInstall.extend(
                [
                    f"binutils-{constants.targetArch}-linux-gnu",
                    f"gcc-{constants.targetArch}-linux-gnu",
                ]
            )

        if packageName:
            listBuildRequiresPackages = self.getListDependentPackages(
                packageName, packageVersion
            )

        pkgUtils = PackageUtils(self.logName, self.logPath)
        rpmFiles = ""
        for package in listRPMsToInstall:
            rpmFile = None
            version = None

            # Get proper package version
            for depPkg in listBuildRequiresPackages:
                (
                    depPkgName,
                    depPkgVersion,
                ) = StringUtils.splitPackageNameAndVersion(depPkg)
                if depPkgName == package:
                    version = depPkgVersion
                    break

            if not version:
                version = SPECS.getData(constants.buildArch).getHighestVersion(
                    package
                )

            if availablePackages is not None:
                basePkg = f"{SPECS.getData(constants.buildArch).getSpecName(package)}-{version}"
                isAvailable = basePkg in availablePackages
            else:
                # if availablePackages is not provided (rear case) it is safe
                # to use findRPMFile()
                isAvailable = True

            if constants.rpmCheck:
                rpmFile = pkgUtils.findRPMFile(
                    package, version, constants.buildArch
                )

            if rpmFile is None:
                # Honor the toolchain list order.
                # if index of depended package ('package') is more
                # then index of the current package that we are
                # building ('packageName'), then we _must_ use published
                # `package` rpm.
                if (
                    packageName
                    and packageName in listRPMsToInstall
                    and listRPMsToInstall.index(packageName)
                    < listRPMsToInstall.index(package)
                ):
                    isAvailable = False
                if isAvailable:
                    rpmFile = pkgUtils.findRPMFile(
                        package, version, constants.buildArch
                    )

            if rpmFile is None:
                if (
                    not usePublishedRPMS
                    or isAvailable
                    or constants.crossCompiling
                ):
                    raise Exception(
                        f"{package}-{version}.{constants.buildArch} not found in available packages"
                    )

                # Safe to use published RPM
                rpmFile = self._findPublishedRPM(
                    package, constants.prevPublishRPMRepo
                )
            if rpmFile is None:
                self.logger.error(
                    f"Unable to find published rpm: {package}"
                )
                raise Exception("Input Error")
            rpmFiles += f" {rpmFile}"
            packages += f" {package}-{version}"

        self.logger.debug(f"{rpmFiles}\n{packages}")
        cmd = f"{self.rpmCommand} -iv --nodeps --force --root {ChrootID} {rpmFiles}"  # noqa: E501

        # If rpm doesn't have zstd support, use rpm from photon_builder image
        if constants.checkIfHostRpmNotUsable():
            cmd = (
                f"docker run --ulimit nofile=1024:1024 --rm -i"
                f" -v {constants.prevPublishRPMRepo}:{constants.prevPublishRPMRepo}"  # noqa: E501
                f" -v {constants.inputRPMSPath}:{constants.inputRPMSPath}"
                f" -v {constants.rpmPath}:{constants.rpmPath} -v {ChrootID}:{ChrootID}"  # noqa: E501
                f" {constants.phBuilderTag}"
                f' /bin/bash -c "{cmd}"'
            )

        self.logger.debug(f"Executing cmd: {cmd}")
        self.cmdUtils.runBashCmd(cmd, logfn=self.logger.debug)
        self.logger.debug(
            f"Successfully installed default toolchain RPMS in Chroot: {ChrootID}"  # noqa: E501
        )

        if packageName:
            self.installExtraToolchainRPMS(chroot, packageName, packageVersion)

        if constants.crossCompiling:
            self.installTargetToolchain(chroot, targetPackageName)

    def installExtraToolchainRPMS(self, sandbox, packageName, packageVersion):
        listOfToolChainPkgs = SPECS.getData(
            constants.buildArch
        ).getExtraBuildRequiresForPackage(packageName, packageVersion)
        if not listOfToolChainPkgs:
            return
        self.logger.debug(
            f"Installing package specific toolchain RPMs for {packageName}: {str(listOfToolChainPkgs)}"
        )
        packages = ""

        rpmFiles = ""
        for package in listOfToolChainPkgs:
            if re.match("openjre*", packageName) is not None or re.match(
                "openjdk*", packageName
            ):
                path = constants.prevPublishXRPMRepo
                sandboxPath = "/publishxrpms"
            else:
                path = constants.prevPublishRPMRepo
                sandboxPath = "/publishrpms"
            rpmFile = self._findPublishedRPM(package, path)
            if rpmFile is None:
                self.logger.error(
                    f"Unable to find rpm {package} in current and previous versions"  # noqa: E501
                )
                raise Exception("Input Error")
            rpmFiles += f" {rpmFile.replace(path, sandboxPath)}"
            packages += f" {package}"

        self.logger.debug(f"Installing custom rpms: {packages}")
        cmd = f"rpm -iv --nodeps --force {rpmFiles}"
        if sandbox.run(cmd, logfn=self.logger.debug):
            self.logger.debug(f"Command Executed: {cmd}")
            self.logger.error("Installing custom toolchains failed")
            raise Exception("RPM installation failed")

    # Install target's core toolchain packages up to 'stopAtPackage' package
    def installTargetToolchain(self, chroot, stopAtPackage=None):
        self.logger.debug("Installing target toolchain RPMS.......")
        pkgUtils = PackageUtils(self.logName, self.logPath)
        rpmFiles = ""
        packages = ""
        ChrootID = chroot.getID()

        for package in constants.listCoreToolChainPackages:
            if stopAtPackage and package == stopAtPackage:
                break
            version = SPECS.getData().getHighestVersion(package)
            basePkg = SPECS.getData().getSpecName(package)
            # install all subpackages of given package
            # for instance: for 'glibc' we want glibc-devel, glibc-tools,
            #               glibc-i18n, etc also to be installed
            subpackages = SPECS.getData().getRPMPackages(basePkg, version)
            for p in subpackages:
                rpmFile = pkgUtils.findRPMFile(
                    p, version, constants.targetArch
                )
                rpmFiles += f" {rpmFile}"
                packages += f" {package}-{version}"

        self.logger.debug(packages)

        cmd = f"mkdir -p {ChrootID}/target-{constants.targetArch}"
        self.cmdUtils.runBashCmd(cmd, logfn=self.logger.debug)

        if rpmFiles != "":
            cmd = (
                f"{self.rpmCommand} -Uv --nodeps --ignorearch --noscripts --root"  # noqa: E501
                f" {ChrootID}/target-{constants.targetArch} {rpmFiles}"
            )
            self.cmdUtils.runBashCmd(cmd, logfn=self.logger.debug)
        self.logger.debug(
            "Successfully installed target toolchain RPMS in chroot: "
            f"{ChrootID}"
        )
