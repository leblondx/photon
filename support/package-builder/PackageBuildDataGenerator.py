#!/usr/bin/env python3

import copy

from collections import OrderedDict
from Logger import Logger
from constants import constants
from SpecData import SPECS


def removeDuplicateEntries(myList):
    return list(OrderedDict.fromkeys(myList))


class PackageBuildDataGenerator(object):

    cycleCount = 0

    def __init__(self, logName=None, logPath=None):
        if logName is None:
            logName = "PackageBuildDataGenerator"
        if logPath is None:
            logPath = constants.logPath
        self.logger = Logger.getLogger(logName, logPath, constants.logLevel)
        self.__mapCyclesToPackageList = {}
        self.__mapPackageToCycle = {}
        self.__buildDependencyGraph = {}
        self.__runTimeDependencyGraph = {}
        self.__sortedPackageList = []
        self.__sortedBuildDependencyGraph = {}

    def getPackageBuildData(self, listPackages):
        basePackages = [SPECS.getData().getBasePkg(pkg) for pkg in listPackages]
        self._readDependencyGraphAndCyclesForGivenPackages(basePackages)
        self._getSortedBuildOrderList()
        return (
            self.__mapCyclesToPackageList,
            self.__mapPackageToCycle,
            self.__sortedPackageList,
        )

    def _findAllPackagesToBuild(self):
        return list(self.__buildDependencyGraph.keys())

    def _createSortListForPkg(self, pkg):
        runTimeDepPkgList = list(set(self.__runTimeDependencyGraph[pkg]))
        runTimeDepPkgList.append(pkg)
        sortListForPkg = []

        for p in runTimeDepPkgList:
            basePkg = SPECS.getData().getBasePkg(p)
            for bPkg in self.__sortedBuildDependencyGraph[basePkg]:
                if bPkg not in sortListForPkg:
                    sortListForPkg.append(bPkg)

        return sortListForPkg

    def _getCircularDependentPackages(self, pkg):
        circularDependentPackages = []
        if pkg in self.__mapPackageToCycle:
            circularDependentPackages.extend(
                self.__mapCyclesToPackageList[self.__mapPackageToCycle[pkg]]
            )
            circularDependentPackages.remove(pkg)
        return circularDependentPackages

    def _getSortedBuildOrderList(self):

        alreadyProcessedPackages = set()
        sortedList = []
        completeListPackagesToBuild = self._findAllPackagesToBuild()
        packageIndexInSortedList = 0
        prevSortListLen = 0

        while completeListPackagesToBuild:

            # find next package to process
            pkg = None
            index = -1
            lenList = len(sortedList)
            for i in range(lenList):
                if sortedList[i] in alreadyProcessedPackages:
                    continue
                pkg = sortedList[i]
                packageIndexInSortedList = i
                break

            if pkg is None:
                pkg = completeListPackagesToBuild.pop()
                packageIndexInSortedList = len(sortedList)

            # creating sort list for package
            sortListForPkg = self._createSortListForPkg(pkg)

            # remove any cyclic packages in sortListForPkg if they already
            # exists in sortedList
            circularDependentPackages = self._getCircularDependentPackages(pkg)
            for p in circularDependentPackages:
                if p in sortedList and p in sortListForPkg:
                    sortListForPkg.remove(p)

            # insert sort list of package in global sorted list
            index = packageIndexInSortedList
            subList = []
            if packageIndexInSortedList > 0:
                subList = sortedList[:packageIndexInSortedList]
            for p in sortListForPkg:
                if p not in subList:
                    sortedList.insert(index, p)
                    index = index + 1

            alreadyProcessedPackages.add(p)

            # Remove duplicate entries in sorted list in intervals
            if (len(sortedList) - prevSortListLen) > 100:
                self.logger.debug("Removing duplicates in sortedList")
                sortedList = removeDuplicateEntries(sortedList)
            else:
                prevSortListLen = len(sortedList)

        self.logger.debug("Removing duplicates in sorted list")
        sortedList = removeDuplicateEntries(sortedList)

        self.logger.debug("Sorted list: ")
        self.logger.debug(sortedList)
        self.__sortedPackageList = sortedList

    def _constructBuildAndRunTimeDependencyGraph(self, basePackage):
        addBuildTimeGraph = basePackage not in self.__buildDependencyGraph
        addRunTimeGraph = basePackage not in self.__runTimeDependencyGraph
        nextPackagesToConstructGraph = set()
        if addBuildTimeGraph:
            dependentRpmPackages = SPECS.getData().getBuildRequiresForPkg(
                basePackage
            )
            dependentPackages = {
                SPECS.getData().getBasePkg(dependentPkg)
                for dependentPkg in dependentRpmPackages
            }
            self.__buildDependencyGraph[basePackage] = dependentPackages
            nextPackagesToConstructGraph.update(dependentPackages)

        if addRunTimeGraph:
            dependentPackages = set()
            for rpmPkg in SPECS.getData().getPackagesForPkg(basePackage):
                dependentRpmPackages = SPECS.getData().getRequiresAllForPkg(
                    rpmPkg
                )
                self.__runTimeDependencyGraph[rpmPkg] = copy.copy(
                    set(dependentRpmPackages)
                )
                for pkg in dependentRpmPackages:
                    dependentPackages.add(SPECS.getData().getBasePkg(pkg))
            nextPackagesToConstructGraph.update(dependentPackages)

        for pkg in nextPackagesToConstructGraph:
            self._constructBuildAndRunTimeDependencyGraph(pkg)

    def _readDependencyGraphAndCyclesForGivenPackages(self, basePackages):
        self.logger.debug("Reading dependency graph to check for cycles")

        for pkg in basePackages:
            self._constructBuildAndRunTimeDependencyGraph(pkg)

        for pkg in self._findAllPackagesToBuild():
            (
                sortedPackageList,
                circularDependentPackages,
            ) = self._topologicalSortPackages(self.__buildDependencyGraph, pkg)
            if circularDependentPackages:
                self.logger.error("Found circular dependency")
                self.logger.error(circularDependentPackages)
                raise Exception("Build Time Circular Dependency")
            self.__sortedBuildDependencyGraph[pkg] = sortedPackageList
        (
            sortedPackageList,
            circularDependentPackages,
        ) = self._topologicalSortPackages(self.__runTimeDependencyGraph)
        if circularDependentPackages:
            self._findCircularDependencies(circularDependentPackages)

    @staticmethod
    def _buildDependentPackages(dependencyGraph, package):
        dependentPackages = {}
        if package is None:
            dependentPackages = copy.deepcopy(dependencyGraph)
        else:
            depPkgs = {package}
            while depPkgs:
                pkg = depPkgs.pop()
                if pkg in dependentPackages:
                    continue
                dependentPackages[pkg] = copy.copy(dependencyGraph[pkg])
                for depPkg in dependencyGraph[pkg]:
                    depPkgs.add(depPkg)
        return dependentPackages

    @staticmethod
    def _buildDependentOfPackages(dependentPackages):
        dependentOfPackage = dict()
        for pkg in dependentPackages:
            if dependentPackages[pkg]:
                for depPkg in dependentPackages[pkg]:
                    if depPkg not in dependentOfPackage:
                        dependentOfPackage[depPkg] = {pkg}
                    else:
                        dependentOfPackage[depPkg].add(pkg)
        return dependentOfPackage

    @staticmethod
    def _topologicalSortPackages(dependencyGraph, package=None):
        sortedPackageList = []
        dependentPackages = PackageBuildDataGenerator._buildDependentPackages(
            dependencyGraph, package
        )
        dependentOfPackage = (
            PackageBuildDataGenerator._buildDependentOfPackages(
                dependentPackages
            )
        )

        """
        Find packages with no dependencies and generate
        dependentof_package edge list
        """
        noDepPackages = {
            pkg for pkg in dependentPackages if not dependentPackages[pkg]
        }
        while noDepPackages:
            pkg = noDepPackages.pop()
            sortedPackageList.append(pkg)
            if pkg in dependentOfPackage:
                for childPkg in list(dependentOfPackage[pkg]):
                    dependentOfPackage[pkg].remove(childPkg)
                    dependentPackages[childPkg].remove(pkg)
                    if not dependentPackages[childPkg]:
                        noDepPackages.add(childPkg)

        circularDependencyGraph = {
            pkg: dependentPackages[pkg]
            for pkg in dependentPackages.keys()
            if dependentPackages[pkg]
        }
        """
        return (non-circular dependent package in sorted order and
        circular dependent package list in a dependencyGraph)
        """
        return sortedPackageList, circularDependencyGraph

    def _constructDependencyMap(self, cyclicDependencyGraph):
        self.logger.debug(
            "Constructing dependency map from circular dependency graph....."
        )
        constructDependencyMap = {}
        for node in cyclicDependencyGraph.keys():
            tmpDepNodeList = {node}
            depNodeList = []

            while tmpDepNodeList:
                currentNode = tmpDepNodeList.pop()
                addDepNodeList = cyclicDependencyGraph[currentNode]
                depNodeList.append(currentNode)
                for depNode in addDepNodeList:
                    if depNode in depNodeList:
                        continue
                    if depNode not in tmpDepNodeList:
                        tmpDepNodeList.add(depNode)

            depNodeList.remove(node)
            constructDependencyMap[node] = depNodeList
        self.logger.debug("Dependency Map:")
        self.logger.debug(constructDependencyMap)

        return constructDependencyMap

    def _findCircularDependencies(self, cyclicDependencyGraph):
        self.logger.debug("Looking for circular dependencies")
        if not cyclicDependencyGraph:
            return
        # step1: construct dependency map from dependency graph
        constructDependencyMap = self._constructDependencyMap(
            cyclicDependencyGraph
        )

        # step2: find cycles in dependency map
        self.logger.debug(
            "Finding and adding cycles using constructed dependency map ..."
        )
        cycleCount = 0
        for node in cyclicDependencyGraph.keys():
            if node not in self.__mapPackageToCycle:
                listDepPkg = constructDependencyMap[node]
                cycPkgs = []
                for depPkg in listDepPkg:
                    x = constructDependencyMap[depPkg]
                    if node in x:
                        cycPkgs.append(depPkg)

                if cycPkgs:
                    cycPkgs.append(node)
                    cycleName = f"cycle{str(PackageBuildDataGenerator.cycleCount)}"
                    PackageBuildDataGenerator.cycleCount += 1
                    for x in cycPkgs:
                        self.__mapPackageToCycle[x] = cycleName
                    self.__mapCyclesToPackageList[cycleName] = cycPkgs
                    self.logger.debug("New circular dependency found:")
                    self.logger.debug(f"{cycleName} " + ",".join(cycPkgs))
                    cycleCount += 1

        if cycleCount > 0:
            self.logger.debug(f"Found {cycleCount} cycles.")
            self.logger.debug(
                "Successfully added all detected circular dependencies "
                "to list."
            )
        else:
            self.logger.debug("No circular dependencies found.")
