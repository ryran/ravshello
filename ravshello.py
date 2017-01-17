#!/usr/bin/python
# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Copyright 2015, 2016, 2017 Ravshello Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------------------

# Modules from standard library
from __future__ import print_function
import argparse
import yaml
import os
import sys

# Custom modules
import _version, string_ops, auth_local, auth_ravello, user_interface


def main():
    """Parse cmdline args, configure prefs, login, and start captive UI."""
    
    ravshelloVersion = "ravshello v{} last mod {}".format(
        _version.__version__, _version.__date__)
    
    # Setup parser
    prog = 'ravshello'
    description = ("Interface with Ravello Systems to create & manage apps "
                   "hosted around the world")
    epilog = ("Version info: {}\n"
              "To report bugs/RFEs: github.com/ryran/ravshello/issues "
              "or rsaw@redhat.com").format(ravshelloVersion)
    p = argparse.ArgumentParser(
        prog=prog, description=description, add_help=False, epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Setup groups for help page:
    grpU = p.add_argument_group('UNIVERSAL OPTIONS')
    grpA = p.add_argument_group(
        'ADMINISTRATIVE FEATURES',
        description="Require that Ravello account user has admin rights")
    
    # Universal opts:
    grpU.add_argument(
        '-h', '--help',  dest='showHelp', action='store_true',
        help="Show this help message and exit")
    grpU.add_argument(
        '-u',  dest='ravelloUser', metavar='USER', default='',
        help=("Explicitly specify Ravello username (will automatically prompt "
              "for a passphrase)"))
    grpU.add_argument(
        '-p', dest='ravelloPass', metavar='PASSWD', default='',
        help=("Explicitly specify a Ravello user password on the command-line "
              "(unsafe on multi-user system)"))
    grpU.add_argument(
        '-k', '--nick', dest='promptNickname', action='store_true',
        help=("Prompt for nickname to use for app-filtering (nickname is "
              "normally determined from the system user name)"))
    grpU.add_argument(
        '-n', '--nocolor', dest='enableColor', action='store_false',
        help="Disable all color terminal enhancements")
    grpU.add_argument('--cfgdir', dest='userCfgDir', metavar='CFGDIR',
        default='~/.ravshello',
        help=("Explicitly specify path to user config directory "
              "(default: '~/.ravshello/')"))
    grpU.add_argument('--cfgfile', dest='cfgFileName', metavar='CFGFILE',
        default='config.yaml',
        help=("Explicitly specify basename of optional yaml config file "
              "containing login credentials, etc (default: 'config.yaml')"))
    grpU.add_argument(
        '--clearprefs', dest='clearPreferences', action='store_true',
        help="Delete prefs.bin in user config directory before starting")
    grpU.add_argument(
        '-q', '--quiet', dest='enableVerboseMessages', action='store_false',
        help="Hide verbose messages during startup")
    grpU.add_argument(
        '-d', '--debug', dest='enableDebugging', action='store_true',
        help="Turn on debugging features to help troubleshoot a problem")
    grpU.add_argument(
        '-V', '--version', action='version', version=ravshelloVersion)
    
    # Admin-only opts:
    grpA.add_argument(
        '-a', '--admin', dest='enableAdminFuncs', action='store_true',
        help="Enable admin functionality")
    grpA.add_argument(
        '-A', '--allapps', dest='showAllApps', action='store_true',
        help=("Show all applications, including ones not associated with your "
              "user (automatically triggers --admin option)"))
    grpA.add_argument(
        '-s', dest='scriptFile', metavar='FILE',
        help=("Specify a script file containing newline-delimited commands "
              "(commands will be executed instead of entering the "
              "interactive shell)"))
    grpA.add_argument(
        'cmdlineArgs', metavar='COMMAND', nargs=argparse.REMAINDER,
        help=("All remaining non-option arguments will be treated as a single "
              "command to execute instead of entering the interactive shell"))
    
    # Build out options namespace
    
    rOpt = p.parse_args()
    if rOpt.showHelp:
        p.print_help()
        sys.exit()
    rOpt.cmdlineArgs = " ".join(rOpt.cmdlineArgs)
    
    rOpt.c = c = string_ops.Printer(rOpt.enableColor,
                                    rOpt.enableVerboseMessages)
    
    # Trigger -a if -A was called
    if rOpt.showAllApps:
        rOpt.enableAdminFuncs = True
     
    rOpt.ravshelloVersion = ravshelloVersion
    
    # Expand userCfgDir in case of tildes; set to default if missing specified dir
    if os.path.isdir(os.path.expanduser(rOpt.userCfgDir)):
        rOpt.userCfgDir = os.path.expanduser(rOpt.userCfgDir)
    else:
        rOpt.userCfgDir = os.path.expanduser('~/.ravshello')
    
    try:
        # Read yaml config to dictionary
        with open(os.path.join(rOpt.userCfgDir, rOpt.cfgFileName)) as f:
            rOpt.cfgFile = yaml.safe_load(f)
    except:
        # Create empty dict if reading config failed
        c.verbose(
            "Note: unable to read configFile '{}'; using defaults"
            .format(os.path.join(rOpt.userCfgDir, rOpt.cfgFileName)))
        rOpt.cfgFile = {}
    
    # Expand sshKeyFile var in case of tildes used; set to none if missing
    if os.path.isfile(os.path.expanduser(rOpt.cfgFile.get('sshKeyFile', ''))):
        rOpt.cfgFile['sshKeyFile'] = os.path.expanduser(
            rOpt.cfgFile['sshKeyFile'])
    else:
        rOpt.cfgFile['sshKeyFile'] = None
    
    # Learner mode can only create apps from blueprints which have
    # one of these strings in their description
    rOpt.learnerBlueprintTag = [
        "#is_learner_blueprint",
        "#learner_bp",
        ]
    
    # More learner mode rules
    rOpt.maxLearnerPublishedApps = 3
    rOpt.maxLearnerActiveVms = 8
    
    print(c.BOLD(
        "Welcome to ravshello, "
        "a shell to provision & manage machines with Ravello!"))
    
    # Liftoff
    # 1.) Establish a local user name to use in ravshello
    #     This name is arbitrary and has nothing to do with Ravello login creds
    #     It is used:
    #       - To construct names for new apps
    #       - To restrict which apps can be seen
    #       - To determine if admin functionality is unlockable (assuming -a or -A)
    rOpt.user = auth_local.authorize_user(rOpt)
    
    # 2.) Use ravello_sdk.RavelloClient() object to log in to Ravello
    rClient = auth_ravello.login(rOpt)
    
    # 3.) Launch the main configShell user interface
    #     Pass it the rOpt namespace full of all our options
    #     Also of course pass it the RavelloClient() object
    user_interface.main(rOpt, rClient)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit()
