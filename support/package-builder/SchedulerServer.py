#!/usr/bin/env python3

import flask

from Scheduler import Scheduler
from constants import constants
from Logger import Logger

SUCCESS = 200
NO_CONTENT = 204
BAD_REQUEST = 400
NOT_ACCEPTABLE = 406

app = flask.Flask(__name__)
mapPackageToCycle = {}

logger = Logger.getLogger("werkzeug", constants.logPath, constants.logLevel)


def shutdownServer():
    logger.disabled = False
    logger.info("Shutting down server ...")
    stopServer = flask.request.environ.get("werkzeug.server.shutdown")
    if stopServer is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    stopServer()


def buildCompleted():
    return not Scheduler.isAnyPackagesCurrentlyBuilding()


@app.route("/package/", methods=["GET"])
def getNextPkgToBuild():
    logger.disabled = False
    pkg = Scheduler.getNextPackageToBuild()
    if not pkg:
        """
        if no package is left to schedule and no package is currently
        building our build is complete either all of them passed
        or some failed
        """
        if buildCompleted():
            logger.info("Package build completed ...")
            shutdownServer()
        logger.disabled = True
        return "", NO_CONTENT

    logger.info(f"Scheduling package {pkg}")
    logger.disabled = True
    return pkg, SUCCESS


@app.route("/notifybuild/", methods=["POST"])
def notifyPackageBuildCompleted():
    logger.disabled = False
    if (
        "status" not in flask.request.json
        or "package" not in flask.request.json
    ):
        return {"message", "missing package or status in request"}, BAD_REQUEST

    if flask.request.json["status"] == 0:
        Scheduler.notifyPackageBuildCompleted(flask.request.json["package"])
        logger.info(f'Build Success {flask.request.json["package"]}')
    elif flask.request.json["status"] == -1:
        Scheduler.notifyPackageBuildFailed(flask.request.json["package"])
        logger.info(f'Build Failed {flask.request.json["package"]}')
    else:
        return {"message", "wrong status"}, NOT_ACCEPTABLE
    logger.disabled = True
    return {"message": "master notified successfully"}, SUCCESS


@app.route("/donelist/", methods=["GET"])
def getDoneList():
    doneList = Scheduler.getDoneList()
    return flask.jsonify(packages=doneList), SUCCESS


@app.route("/mappackagetocycle/", methods=["GET"])
def getMapPackageToCycle():
    return mapPackageToCycle, SUCCESS


@app.route("/constants/", methods=["GET"])
def getConstants():
    constant_dict = {
        "specPath": constants.specPath,
        "sourcePath": constants.sourcePath,
        "rpmPath": constants.rpmPath,
        "sourceRpmPath": constants.sourceRpmPath,
        "topDirPath": constants.topDirPath,
        "logPath": constants.logPath,
        "logLevel": constants.logLevel,
        "dist": constants.dist,
        "buildNumber": constants.buildNumber,
        "releaseVersion": constants.releaseVersion,
        "prevPublishRPMRepo": constants.prevPublishRPMRepo,
        "prevPublishXRPMRepo": constants.prevPublishXRPMRepo,
        "buildRootPath": constants.buildRootPath,
        "pullsourcesURL": constants.pullsourcesURL,
        "extrasourcesURLs": constants.extrasourcesURLs,
        "buildPatch": constants.buildPatch,
        "inputRPMSPath": constants.inputRPMSPath,
        "rpmCheck": constants.rpmCheck,
        "rpmCheckStopOnError": constants.rpmCheckStopOnError,
        "publishBuildDependencies": constants.publishBuildDependencies,
        "packageWeightsPath": constants.packageWeightsPath,
        "userDefinedMacros": constants.userDefinedMacros,
        "katBuild": constants.katBuild,
        "canisterBuild": constants.canisterBuild,
        'acvpBuild': constants.acvpBuild,
        "tmpDirPath": constants.tmpDirPath,
        "buildArch": constants.buildArch,
        "currentArch": constants.currentArch,
    }
    return constant_dict, SUCCESS


def startServer():
    #  if no packages to build then return
    if Scheduler.isAllPackagesBuilt():
        return
    logger.info("Starting Server ...")
    try:
        logger.disabled = True
        app.run(host="0.0.0.0", port="80", debug=False, use_reloader=False)
    except Exception as e:
        logger.exception(e)
        logger.error("unable to start server")
        logger.error("")
