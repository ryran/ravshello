# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
import sys
from getpass import getpass

# Custom modules
import rsaw_ascii
try:
    import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/tree/experimental\n")
    raise
from local_config import RavelloLogin 


cfgFile = RavelloLogin()
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


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    pwd = getpass(prompt=prompt)
    while not len(pwd):
        if defaultPass:
            pwd = defaultPass
        else:
            pwd = getpass(prompt="    You must enter a passphrase: ")
    return pwd


def login(opt):
    """Determine Ravello credentials and login via RavelloClient object"""
    global ravshOpt, c
    ravshOpt = opt    
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    
    # Create client object
    ravClient = ravello_sdk.RavelloClient()
    
    verbose("\nConnecting to Ravello . . .")
    
    # If necessary, get Ravello username from configfile or prompt
    if not ravshOpt.ravelloUser:
        if cfgFile.ravelloUser:
            ravshOpt.ravelloUser = cfgFile.ravelloUser
        else:
            ravshOpt.ravelloUser = raw_input(c.CYAN("  Enter Ravello username: "))
    
    # If necessary, get Ravello password from configfile or prompt
    if not ravshOpt.ravelloPass:
        if cfgFile.ravelloPass:
            ravshOpt.ravelloPass = cfgFile.ravelloPass
        else:
            ravshOpt.ravelloPass = get_passphrase(c.CYAN("  Enter Ravello passphrase: "))
    
    # Try to log in
    try:
        ravClient.login(ravshOpt.ravelloUser, ravshOpt.ravelloPass)
    except:
        print(c.RED("  Logging in to Ravello failed!"))
        print("\nIf you're sure your Ravello credentials are correct, try updating ravshello")
        if cfgFile.unableToLoginAdditionalMsg:
            print(cfgFile.unableToLoginAdditionalMsg)
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
