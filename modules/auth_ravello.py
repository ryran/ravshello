# -*- coding: utf-8 -*-
# Copyright 2015, 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from getpass import getpass
from sys import exit, stderr

# Custom modules
from . import string_ops as c
from . import cfg
try:
    from . import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/blob/ravshello-stable/lib/ravello_sdk.py\n")
    raise


def quit_login_failed():
    message = cfg.cfgFile.get('unableToLoginMsg',
        cfg.cfgFile.get('unableToLoginAdditionalMsg',
            "If you're certain Ravello credentials are correct, try updating ravshello"))
    print(c.RED("  Logging in to Ravello failed!\n"), file=stderr)
    print(message, file=stderr)
    exit(5)


def get_username(prompt="Enter username: ", defaultUser=None):
    """Prompt for a username, allowing pre-populated *defaultUser*."""
    if cfg.opts.neverPromptCreds:
        quit_login_failed()
    user = raw_input(prompt)
    while not len(user):
        if defaultUser:
            user = defaultUser
        else:
            user = raw_input("    You must enter a username: ")
    return user


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    if cfg.opts.neverPromptCreds:
        quit_login_failed()
    passwd = getpass(prompt)
    while not len(passwd):
        if defaultPass:
            passwd = defaultPass
        else:
            passwd = getpass("    You must enter a passphrase: ")
    return passwd


def login():
    """Determine Ravello credentials and login via RavelloClient object"""
    # Simplify
    rOpt = cfg.opts
    # Create client object
    rClient = ravello_sdk.RavelloClient(retries=rOpt.maxClientRetries)
    c.verbose("\nConnecting to Ravello . . .", file=stderr)
    cfgUser = cfg.cfgFile.get('ravelloUser', None)
    cfgPass = cfg.cfgFile.get('ravelloPass', None)
    profiles = cfg.cfgFile.get('userProfiles', {})
    user = passwd = userFrom = profile = None
    # Set default cb & app prefix
    cfg.appCostBucket = cfg.cfgFile.get('appCostBucket', None)
    cfg.appnameNickPrefix = cfg.cfgFile.get('appnameNickPrefix', None)
    # If necessary, get Ravello *username* from configfile or prompt
    try:
        profile = profiles[rOpt.ravelloUser]
        user = profile['ravelloUser']
        passwd = profile.get('ravelloPass')
        userFrom = 'profile'
    except:
        user = rOpt.ravelloUser
    if not user:
        if cfgUser:
            user = cfgUser
            userFrom = 'cfg'
        else:
            try:
                user = profiles[profiles['defaultProfile']]['ravelloUser']
                userFrom = 'defaultProfile'
            except:
                user = get_username(c.CYAN("  Enter Ravello username: "))
    # Set per-user cb
    if userFrom == 'profile':
        try:
            cfg.appCostBucket = profile['appCostBucket']
            cfg.appnameNickPrefix = profile['appnameNickPrefix']
        except:
            pass
    elif userFrom == 'defaultProfile':
        try:
            cfg.appCostBucket = profiles[profiles['defaultProfile']]['appCostBucket']
            cfg.appnameNickPrefix = profiles[profiles['defaultProfile']]['appnameNickPrefix']
        except:
            pass
    # If necessary, get Ravello *password* from configfile or prompt
    if rOpt.ravelloPass:
        passwd = rOpt.ravelloPass
    elif userFrom == 'profile':
        pass
    elif userFrom == 'defaultProfile':
        try:
            passwd = profiles[profiles['defaultProfile']]['ravelloPass']
        except:
            pass
    elif userFrom == 'cfg':
        passwd = cfgPass
    if not passwd:
        passwd = get_passphrase(c.CYAN("  Enter Ravello passphrase: "))
    rOpt.ravelloUser = user
    rOpt.ravelloPass = passwd
    try:
        rClient.login(rOpt.ravelloUser, rOpt.ravelloPass)
    except:
        quit_login_failed()
    if rOpt.printWelcome:
        print(c.GREEN("  Logged in to Ravello as "), end="", file=stderr)
        if rOpt.enableAdminFuncs:
            print(c.YELLOW("ADMIN"), end="", file=stderr)
            if rOpt.showAllApps:
                print(" " + c.bgRED("[global app visiblity]"), file=stderr)
            else:
                print(file=stderr)
        else:
            print(c.GREEN("LEARNER"), file=stderr)
    return rClient
