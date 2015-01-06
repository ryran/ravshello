#!/usr/bin/python
# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Copyright 2015 Ravshello Authors
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

from __future__ import print_function

ravshelloVersion = "ravshello v1.2.5 last mod 2015/01/06"

# Modules from standard library
import argparse
import os
import sys

# Custom ravshello modules
import rsaw_ascii, auth_local, auth_ravello, user_interface


if __name__ == "__main__":
    
    # Setup parser
    prog = 'ravshello'
    description = "Interface with Ravello Systems to create & manage apps hosted around the world"
    epilog = ("Version info: {}\n".format(ravshelloVersion) +
              "To report bugs/RFEs: github.com/ryran/ravshello/issues or rsaw@redhat.com")
    
    p = argparse.ArgumentParser(prog=prog, description=description, 
                                add_help=False, epilog=epilog,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Setup groups for help page:
    grpU = p.add_argument_group('UNIVERSAL OPTIONS')
    grpA = p.add_argument_group('ADMINISTRATIVE FEATURES',
                                description="Requires user on Ravello account have admin access")
    
    # Universal opts:
    grpU.add_argument('-h', '--help',  dest='showHelp', action='store_true',
        help="Show this help message and exit")
    grpU.add_argument('-u',  dest='ravelloUser', metavar='USER', default='',
        help="Explicitly specify Ravello username (will automatically prompt " +
             "for a passphrase)")
    grpU.add_argument('-p', dest='ravelloPass', metavar='PASSWD', default='',
        help="Explicitly specify a Ravello user password on the command-line " +
             "(unsafe on multi-user system)")
    grpU.add_argument('-k', '--nick', dest='promptNickname', action='store_true',
        help="Prompt for nickname to use for app-filtering (nickname is normally " + 
             "determined from the system user name)")
    grpU.add_argument('-n', '--nocolor', dest='enableAsciiColors', action='store_false',
        help="Disable all color terminal enhancements")
    grpU.add_argument('--clearprefs', dest='clearPreferences', action='store_true',
        help="Delete ~/.ravshello/prefs.bin before starting")
    grpU.add_argument('-q', '--quiet', dest='verboseMessages', action='store_false',
        help="Hide verbose messages during startup")
    grpU.add_argument('-V', '--version', action='version', version=ravshelloVersion)
    
    # Admin-only opts:
    grpA.add_argument('-a', '--admin', dest='enableAdminFuncs', action='store_true',
        help="Enable admin functionality")
    grpA.add_argument('-A', '--allapps', dest='showAllApps', action='store_true',
        help="Show all applications, including ones not associated with your " +
             "user (automatically triggers --admin option)") 
    grpA.add_argument('-s', dest='scriptFile', metavar='FILE',
        help="Specify a script file containing newline-delimited commands " +
             "(commands will be executed instead of entering the interactive shell)")
    grpA.add_argument('cmdlineArgs', metavar='COMMAND', nargs=argparse.REMAINDER,
        help="All remaining non-option arguments will be treated as a single " +
             "command to execute instead of entering the interactive shell")
    
    # Parse args out to namespace
    ravshOpt = p.parse_args()
    
    # Help?
    if ravshOpt.showHelp:
        p.print_help()
        sys.exit()
    
    # Unpack COMMAND
    ravshOpt.cmdlineArgs = " ".join(ravshOpt.cmdlineArgs)
    
    # Trigger -a if -A was called
    if ravshOpt.showAllApps:
        ravshOpt.enableAdminFuncs = True
        
    # Set all other default options
    
    ravshOpt.ravshelloVersion = ravshelloVersion
        
    # Set config dir
    ravshOpt.userCfgDir = os.path.expanduser('~/.ravshello')
    
    # Can create apps in learner mode only from blueprints with one of these in their description
    ravshOpt.learnerBlueprintTag = ['#is_learner_blueprint', '#learner_bp']

    # Set more stuff for learner enforcement
    ravshOpt.maxLearnerPublishedApps = 3
    ravshOpt.maxLearnerActiveVms = 8
    
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    
    # Print welcome
    print(c.BOLD("Welcome to ravshello, a shell to provision & manage VMs with Ravello!"))
    
    # Liftoff
    try:
        
        # 1.) Establish a local user name to use in ravshello
        #     This name is arbitrary and has nothing to do with Ravello login creds
        #     It is used:
        #       - To construct names for new apps
        #       - To restrict which apps can be seen
        #       - To determine if admin functionality is unlockable (assuming -a or -A)
        ravshOpt.user = auth_local.authorize_user(ravshOpt)
        
        # 2.) Use ravello_sdk.RavelloClient() object to log in to Ravello
        ravClient = auth_ravello.login(ravshOpt)
        
        # 3.) Launch the main configShell user interface
        #     Pass it the ravshOpt namespace full of all our options
        #     Also of course pass it the RavelloClient() object
        user_interface.main(ravshOpt, ravClient)
    
    except KeyboardInterrupt:
        print()
        sys.exit()
