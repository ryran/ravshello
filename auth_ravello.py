# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
import sys

# Custom modules
import rsaw_ascii
try:
    from ravello_sdk import *
except:
    print("Missing a required python module (ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk\n")
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


def login(opt):
    
    global ravshOpt, c
    ravshOpt = opt    
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    
    # Create client object
    ravClient = RavelloClient()
    
    verbose("\nConnecting to Ravello . . .")
    
    # Get Ravello user creds from cmdline or configfile using admin username/pass
    if cfgFile.ravelloUser and not ravshOpt.ravelloUser:
        ravshOpt.ravelloUser = cfgFile.ravelloUser
    if cfgFile.ravelloPass and not ravshOpt.ravelloPass:
        ravshOpt.ravelloPass = cfgFile.ravelloPass
    try:
        ravClient.login(ravshOpt.ravelloUser, ravshOpt.ravelloPass)
    except:
        print(c.RED("  Unable to login to Ravello!"))
        print("\nIf you have your own Ravello login, you should use the -u & -p options" +
              "\nOtherwise, try updating ravshello")
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
