# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
import pwd
import os
import ConfigParser

# Custom modules
import rsaw_ascii


ravshOpt = c = None


def verbose(message, end=None):
    if ravshOpt.verboseMessages:
        if end is not None:
            print(c.magenta(message), end=end)
        else:
            print(c.magenta(message))


def authorize_user(opt):
    global ravshOpt, c
    ravshOpt = opt    
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    cfg = ConfigParser.ConfigParser()
    cfg.read(ravshOpt.userCfgDir + '/ravshello.conf')
    try:
        cNick = cfg.get('ui', 'nickname')
    except:
        cNick = None
    verbose("\nDetermining nickname . . .")
    verbose("  (Nickname will be prepended to names of any apps you create)")
    verbose("  (Nickname will be used to restrict which app names you can see)")
    if ravshOpt.promptNickname:
        nick = raw_input(c.CYAN("  Enter nickname: "))
        user = rsaw_ascii.replace_bad_chars_with_underscores(nick)
        if nick != user:
            print(c.yellow("    Invalid characters replaced w/underscores"))
        print(c.GREEN("  Using entry '{}' for nickname".format(user)))
    elif cNick:
        user = cNick
        print(c.GREEN("  Using configfile-specified nick '{}' for nickname".format(user)))
    else:
        user = pwd.getpwuid(os.getuid()).pw_name
        print(c.GREEN("  Using system user '{}' for nickname".format(user)))
    return user
