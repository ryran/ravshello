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
from sys import exit, stderr
from glob import glob

# Custom modules
from modules import string_ops as c
from modules import ravello_cache
from modules import auth_local, auth_ravello, user_interface, cfg


class CustomFormatter(argparse.RawDescriptionHelpFormatter):
    """This custom formatter eliminates the duplicate metavar in help lines."""
    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts = []
            if action.nargs == 0:
                parts.extend(action.option_strings)
            else:
                default = action.dest.upper()
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append('%s' % option_string)
                parts[-1] += ' %s'%args_string
            return ', '.join(parts)


class Loader(yaml.Loader):
    """From http://stackoverflow.com/a/9577670."""
    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]
        super(Loader, self).__init__(stream)
    def include(self, node):
        filename = os.path.expanduser(self.construct_scalar(node))
        if not filename.startswith('/'):
            filename = os.path.join(self._root, filename)
        with open(filename, 'r') as f:
            return yaml.load(f, Loader)

# Add yaml custom !include handler
Loader.add_constructor('!include', Loader.include)


def apply_config_file(filepath):
    """Update cfgFile dict w/yaml config file, ignoring missing files."""
    try:
        with open(filepath) as f:
            cfg.cfgFile.update(yaml.load(f, Loader))
    except IOError as e:
        if e.strerror == 'No such file or directory':
            pass
        else:
            print(c.yellow("Ignoring config file '{}'; IOError: {}"
                .format(filepath, e.strerror)), file=stderr)
    except TypeError as e:
        if e.message == "'NoneType' object is not iterable":
            # This means it's an empty config file
            pass
        else:
            raise
    except:
        print(c.red("Fatal error parsing config file '{}'\n"
            .format(filepath)), file=stderr)
        raise


def main():
    """Parse cmdline args, configure prefs, login, and start captive UI."""
    # Setup parser
    description = ("Interface with Ravello Systems to create & manage apps "
                   "hosted around the world")
    epilog = ("ENVIRONMENT VARIABLES:\n"
              "  Various printing commands in {} make use of the RAVSH_EDITOR variable\n"
              "  if it is present, falling back to the EDITOR variable. If that's empty, the\n"
              "  fall-back process is to use: gvim, vim, and finally less.\n\n"
              "VERSION:\n"
              "  {}\n"
              "  Report bugs/RFEs/feedback at https://github.com/ryran/ravshello/issues"
              .format(cfg.prog, cfg.version))
    p = argparse.ArgumentParser(
        prog=cfg.prog,
        description=description,
        add_help=False,
        epilog=epilog,
        formatter_class=lambda prog: CustomFormatter(prog))
    
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
        '-u',  '--user', dest='ravelloUser', metavar='USER', default='',
        help=("Explicitly specify Ravello username or profile name from {} "
              "config file (will automatically prompt for passphrase if none "
              "is present in cfgfile)".format(cfg.defaultUserCfgFile)))
    grpU.add_argument(
        '-p', '--passwd', dest='ravelloPass', metavar='PASSWD', default='',
        help=("Explicitly specify a Ravello user password on the command-line "
              "(unsafe on multi-user system)"))
    grpU_0 = grpU.add_mutually_exclusive_group()
    grpU_0.add_argument(
        '-k', '--nick', dest='nick',
        help=("Explicitly specify a nickname to use for app-filtering "
              "(nickname is normally determined from the system user name "
              "and is used to hide applications that don't start with "
              "'k:NICK__'; any apps created will also have that tag prefixed "
              "to their name; see also 'nickname' and 'appnameNickPrefix' "
              "config directives in /usr/share/{}/config.yaml)".format(cfg.prog)))
    grpU_0.add_argument(
        '--prompt-nick', dest='promptNickname', action='store_true',
        help="Prompt for nickname to use for app-filtering")
    grpU.add_argument(
        '--never-prompt-creds', dest='neverPromptCreds', action='store_true',
        help=("Never prompt for Ravello user or pass credentials if missing; "
              "instead exit with standard 'Logging in to Ravello failed' message "
              "and set exit code '5' (note that using this will override an "
              "explicit 'neverPromptCreds=false' setting from a config file)"))
    grpU.add_argument(
        '-n', '--nocolor', dest='enableColor', action='store_false',
        help="Disable all color terminal enhancements")
    grpU.add_argument('--cfgdir', dest='userCfgDir', metavar='CFGDIR',
        default=cfg.defaultUserCfgDir,
        help=("Explicitly specify path to user config directory "
              "(default: '{}')".format(cfg.defaultUserCfgDir)))
    grpU.add_argument('--cfgfile', dest='cfgFileName', metavar='CFGFILE',
        default=cfg.defaultUserCfgFile,
        help=("Explicitly specify basename of optional per-user yaml config file "
              "containing login credentials & other settings (default: '{default}'); "
              "note that this will be created in CFGDIR; also note that this "
              "file will be read AFTER /usr/share/{prog}/config.yaml & "
              "/etc/{prog}/config.yaml"
              .format(default=cfg.defaultUserCfgFile, prog=cfg.prog)))
    grpU.add_argument(
        '--clearprefs', dest='clearPreferences', action='store_true',
        help="Delete prefs.bin in per-user CFGDIR before starting")
    grpU.add_argument(
        '-q', '--quiet', dest='enableVerbose', action='store_false',
        help="Hide verbose messages during startup")
    grpU.add_argument(
        '-Q', '--more-quiet', dest='printWelcome', action='store_false',
        help=("A superset of the --quiet option; also hides various non-verbose "
              "welcome messages during startup"))
    grpU.add_argument(
        '-d', '--debug', dest='enableDebugging', action='store_true',
        help=("Turn on debugging features to help troubleshoot a problem "
              "(critically, this disables some ConfigShell exception-handling "
              "so that errors in commands will cause {} to exit)"
              .format(cfg.prog)))
    grpU.add_argument(
        '-D', '--directsdk', action='store_true',
        help=("Replaces the standard {} interface with a shell that provides "
              "direct access to the Ravello SDK (note that this shell respects "
              "the --stdin & --scripts options, as well as any cmdline args)"
              .format(cfg.prog)))
    grpU.add_argument(
        '-V', '--version', action='version', version=cfg.version)
    
    # Admin-only opts:
    grpA.add_argument(
        '-a', '--admin', dest='enableAdminFuncs', action='store_true',
        help="Enable admin functionality")
    grpA.add_argument(
        '-A', '--allapps', dest='showAllApps', action='store_true',
        help=("Show all applications, including ones not associated with your "
              "user (automatically triggers --admin option)"))
    grpA_0 = grpA.add_mutually_exclusive_group()
    grpA_0.add_argument(
        '-0', '--stdin', dest='useStdin', action='store_true',
        help=("Enable reading newline-delimited commands from stdin "
              "(these commands will be executed instead of entering the "
              "interactive shell -- automatic exit after last cmd)"))
    grpA_0.add_argument(
        '-s', '--script', dest='scriptFile', metavar='FILE',
        help=("Specify a script file containing newline-delimited "
              "commands (these commands will be executed instead of entering "
              "the interactive shell -- automatic exit after last cmd)"))
    grpA.add_argument(
        'cmdlineArgs', metavar='COMMANDS', nargs=argparse.REMAINDER,
        help=("If any additional cmdline args are present, each shell word "
              "will be treated as a separate command and they will all be "
              "executed prior to entering the interactive shell (ensure "
              "each cmd is quoted to protect from shell expansion!)"))
    
    # Build out options namespace
    cfg.opts = rOpt = p.parse_args()
    
    # Halp-quit
    if rOpt.showHelp:
        p.print_help()
        exit()
    
    # Trigger -q if -Q was called
    if not rOpt.printWelcome:
        rOpt.enableVerbose = False
    
    # Setup color/verbosity
    c.enableColor = rOpt.enableColor
    c.enableVerbose = rOpt.enableVerbose
    c.enableDebug = rOpt.enableDebugging
    
    # Trigger -a if -A was called
    if rOpt.showAllApps:
        rOpt.enableAdminFuncs = True
    
    if not rOpt.enableAdminFuncs:
        if rOpt.cmdlineArgs or rOpt.scriptFile or rOpt.useStdin:
            print(c.red("Sorry! Only admins are allowed to use {} non-interactively".format(cfg.prog)), file=stderr)
            exit(1)
        if rOpt.directsdk:
            print(c.red("Sorry! Only admins are allowed to use the direct SDK shell!"), file=stderr)
            exit(1)
    
    # Print warnings about incompatible options
    if rOpt.useStdin and rOpt.cmdlineArgs:
        print(c.yellow("Ignoring cmdline-args because -0/--stdin was requested"), file=stderr)
    elif rOpt.scriptFile and rOpt.cmdlineArgs:
        print(c.yellow("Ignoring cmdline-args because -s/--script was requested"), file=stderr)
    
    # Expand userCfgDir in case of tildes; set to default if missing specified dir
    if os.path.isdir(os.path.expanduser(rOpt.userCfgDir)):
        rOpt.userCfgDir = os.path.expanduser(rOpt.userCfgDir)
    else:
        rOpt.userCfgDir = os.path.expanduser(cfg.defaultUserCfgDir)
    
    # Read package config file
    apply_config_file('/usr/share/{}/config.yaml'.format(cfg.prog))
    # Read system config file
    apply_config_file('/etc/{}/config.yaml'.format(cfg.prog))
    # Read user config file
    apply_config_file(os.path.join(rOpt.userCfgDir, rOpt.cfgFileName))
    # Do some checking of cfgfile options
    if cfg.cfgFile:
        # Handle include files
        includes = cfg.cfgFile.get('includes', [])
        if isinstance(includes, list):
            # Handle glob-syntax
            L = []
            for filepath in includes:
                L.extend(glob(os.path.expanduser(filepath)))
            for filepath in L:
                apply_config_file(filepath)
        else:
            print(c.yellow(
                "Error: Ignoring configFile `includes` directive because it's not a list\n"
                "  See /usr/share/{}/config.yaml for example".format(cfg.prog)), file=stderr)
        # Validate pre-run commands
        preRunCommands = cfg.cfgFile.get('preRunCommands', [])
        if not isinstance(preRunCommands, list):
            print(c.yellow(
                "Error: Ignoring configFile `preRunCommands` directive because it's not a list\n"
                "  See /usr/share/{}/config.yaml for example".format(cfg.prog)), file=stderr)
            del cfg.cfgFile['preRunCommands']
        # Validate neverPromptCreds
        neverPromptCreds = cfg.cfgFile.get('neverPromptCreds', False)
        if isinstance(neverPromptCreds, bool):
            if neverPromptCreds:
                rOpt.neverPromptCreds = True
        else:
            print(c.yellow(
                "Error: Ignoring configFile `neverPromptCreds` directive because it's not a boolean\n"
                "  See /usr/share/{}/config.yaml for example".format(cfg.prog)), file=stderr)
    
    # Set sshKeyFile var to none if missing
    cfg.cfgFile['sshKeyFile'] = cfg.cfgFile.get('sshKeyFile', None)
    
    if rOpt.printWelcome:
        print(c.BOLD("Welcome to {}!".format(cfg.prog)), file=stderr)
    
    # Liftoff
    # 1.) Establish a local user name to use in ravshello
    #     This name is arbitrary and has nothing to do with Ravello login creds
    #     It is used:
    #       - To construct names for new apps
    #       - To restrict which apps can be seen
    #       - To determine if admin functionality is unlockable (assuming -a or -A)
    cfg.user = auth_local.authorize_user()
    
    # 2.) Use ravello_sdk.RavelloClient() object to log in to Ravello
    cfg.rClient = auth_ravello.login()
    cfg.rCache = ravello_cache.RavelloCache(cfg.rClient)
    
    # 3.) Launch main configShell user interface
    #     It will read options and objects from the cfg module
    user_interface.main()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(file=stderr)
        exit()
