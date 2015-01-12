# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
import sys
from getpass import getpass
import ConfigParser

# Custom modules
import rsaw_ascii
try:
    import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/tree/experimental\n")
    raise

ravshOpt = c = None


def verbose(message, end=None):
    if ravshOpt.verboseMessages:
        if end is not None:
            print(c.magenta(message), end=end)
        else:
            print(c.magenta(message))


def is_admin():
    if ravshOpt.enableAdminFuncs:
        return True
    else:
        return False


def get_username(prompt="Enter username: ", defaultUser=None):
    """Prompt for a username, allowing pre-populated *defaultUser*."""
    user = raw_input(prompt)
    while not len(user):
        if defaultUser:
            user = defaultUser
        else:
            user = raw_input("    You must enter a username: ")
    return user


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    passwd = getpass(prompt)
    while not len(passwd):
        if defaultPass:
            passwd = defaultPass
        else:
            passwd = getpass("    You must enter a passphrase: ")
    return passwd


def login(opt):
    """Determine Ravello credentials and login via RavelloClient object"""
    global ravshOpt, c
    ravshOpt = opt    
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    
    # Create client object
    ravClient = ravello_sdk.RavelloClient()
    
    verbose("\nConnecting to Ravello . . .")
    
    cfg = ConfigParser.ConfigParser()
    cfg.read(ravshOpt.userCfgDir + '/ravshello.conf')
    cUser = cPass = cMesg = None
    try:
        cUser = cfg.get('login', 'ravelloUser')
        cPass = cfg.get('login', 'ravelloPass')
        cMesg = cfg.get('login', 'unableToLoginAdditionalMsg')
    except:
        pass
    
    # If necessary, get Ravello username from configfile or prompt
    if not ravshOpt.ravelloUser:
        if cUser:
            ravshOpt.ravelloUser = cUser
        else:
            ravshOpt.ravelloUser = get_username(c.CYAN("  Enter Ravello username: "))
    
    # If necessary, get Ravello password from configfile or prompt
    if not ravshOpt.ravelloPass:
        if cPass:
            ravshOpt.ravelloPass = cPass
        else:
            ravshOpt.ravelloPass = get_passphrase(c.CYAN("  Enter Ravello passphrase: "))
    
    # Try to log in
    try:
        ravClient.login(ravshOpt.ravelloUser, ravshOpt.ravelloPass)
    except:
        print(c.RED("  Logging in to Ravello failed!"))
        print("\nIf you're sure your Ravello credentials are correct, try updating ravshello")
        if cMesg:
            print(cMesg)
        sys.exit(5)
    del ravshOpt.ravelloUser, ravshOpt.ravelloPass
    
    print(c.GREEN("  Logged in to Ravello as "), end='')
    if is_admin():
        print(c.YELLOW("ADMIN"), end="")
        if ravshOpt.showAllApps:
            print(" " + c.bgRED("[global app visiblity]"))
        else:
            print()
    else:
        print(c.GREEN("LEARNER"))
    
    return ravClient
