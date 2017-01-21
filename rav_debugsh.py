# -*- coding: utf-8 -*-
# Copyright 2015, 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from datetime import datetime
from getpass import getpass
import json
import subprocess
import time
import sys
import yaml
import os
import pydoc
import inspect
from sys import stdout, stdin
from pydoc import pager
from time import sleep, time
from os import path, makedirs, chmod, remove
from datetime import datetime, date
from getpass import getpass
from calendar import month_name
from operator import itemgetter
import termios
import re


# Custom modules
from modules import string_ops as c
from modules import ui_methods, cfg, ravello_cache
try:
    from modules import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/blob/ravshello-stable/lib/ravello_sdk.py\n")
    raise


# Helper functions

def get_username(prompt="Enter username: ", defaultUser=None):
    """Prompt for a username, allowing pre-populated *defaultUser*."""
    user = raw_input(prompt)
    while not len(user):
        if defaultUser:
            user = defaultUser
        else:
            user = raw_input("  You must enter a username: ")
    return user


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    passwd = getpass(prompt)
    while not len(passwd):
        if defaultPass:
            passwd = defaultPass
        else:
            passwd = getpass("  You must enter a passphrase: ")
    return passwd


print(c.magenta("Note, you should import with: from rav_debugsh import *"))
print(c.cyan("Assuming that, get started by running:"))
print(c.CYAN("    r,R,c = go()"))

def go():
    r = ravello_sdk.RavelloClient()
    R = ravello_cache.RavelloCache(r)
    defaultCfgFile = os.path.join(cfg.defaultUserCfgDir, cfg.defaultUserCfgFile)
    try:
        with open(os.path.expanduser(defaultCfgFile)) as f:
            config = yaml.safe_load(f)
    except:
        user = passwd = None
    else:
        user = config.get('ravelloUser', None)
        passwd = config.get('ravelloPass', None)

    if not user:
        user = get_username(c.CYAN("Enter Ravello username: "))
    
    if not passwd:
        passwd = get_passphrase(c.CYAN("Enter Ravello passphrase: "))
    
    try:
        r.login(user, passwd)
    except:
        print(c.RED("Logging in to Ravello failed!"))
    else:
        print(c.GREEN("Logged in to Ravello as {}\n".format(user)))
        print(c.green("r: {}\n".format(r)))
        print(c.green("R: {}\n".format(R)))
        print(c.green("c: {}\n".format(c)))
        print(c.green(inspect.getsource(a)))
        print(c.green(inspect.getsource(A)))
    return r, R, c

def a(jsonInput):
    print(json.dumps(jsonInput, indent=4))

def A(jsonInput):
    pydoc.pager(json.dumps(jsonInput, indent=4))
