# -*- coding: utf-8 -*-
# Copyright 2015, 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
import pwd
import os
from sys import stderr

# Custom modules
from . import string_ops as c
from . import cfg

def authorize_user():
    cfgUser = cfg.cfgFile.get('ravelloUser', None)
    cfgNick = cfg.cfgFile.get('nickname', None)
    profiles = cfg.cfgFile.get('userProfiles', {})
    c.verbose("\nDetermining nickname . . .", file=stderr)
    c.verbose("  (Nickname will be prepended to names of any apps you create)", file=stderr)
    c.verbose("  (Nickname will be used to restrict which app names you can see)", file=stderr)
    nick = None
    try:
        nick = profiles[cfg.opts.ravelloUser]['nickname']
    except:
        if not (cfg.opts.ravelloUser or cfgUser):
            try:
                nick = profiles[profiles['defaultProfile']]['nickname']
            except:
                pass
    if cfg.opts.promptNickname:
        nick = raw_input(c.CYAN("  Enter nickname: "))
        user = c.replace_bad_chars_with_underscores(nick)
        if nick != user:
            print(c.yellow("    Invalid characters replaced w/underscores"), file=stderr)
        print(c.GREEN("  Using input '{}' for nickname".format(user)), file=stderr)
    elif cfg.opts.nick is not None:
        nick = cfg.opts.nick
        user = c.replace_bad_chars_with_underscores(nick)
        if nick != user:
            print(c.yellow("    Invalid characters replaced w/underscores"), file=stderr)
        print(c.GREEN("  Using cmdline arg '{}' for nickname".format(user)), file=stderr)
    elif nick is not None:
        user = nick
        print(c.GREEN("  Using profile-specified '{}' for nickname".format(user)), file=stderr)
    elif cfgNick is not None:
        user = cfgNick
        print(c.GREEN("  Using configfile-specified '{}' for nickname".format(user)), file=stderr)
    else:
        user = pwd.getpwuid(os.getuid()).pw_name
        print(c.GREEN("  Using system user '{}' for nickname".format(user)), file=stderr)
    return user
