# -*- coding: utf-8 -*-
# Copyright 2015, 2016, 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from sys import stdout, stdin, stderr
from pydoc import pager, pipepager
from time import sleep, time
from stat import S_ISDIR
from os import path, makedirs, chmod, remove, stat
from glob import glob
from datetime import datetime, date
from calendar import month_name
from operator import itemgetter
from textwrap import dedent
import json
import subprocess
import termios
import re
from copy import deepcopy

# Modules not from standard library, but widely available
try:
    from configshell_fb import shell as cfshell, ConfigNode, is_rsaw_cfshell
except:
    print("Missing proper version of required python module (rsaw's configshell_fb)\n"
          "Get it from: https://github.com/ryran/configshell-fb.git\n"
          "(Do system install or symlink into ravshello-working-dir/configshell_fb)\n")
    raise
# Remove configshell commands that we don't need or want
del ConfigNode.ui_command_pwd
del ConfigNode.ui_command_bookmarks
del ConfigNode.ui_complete_bookmarks

# Custom modules
from . import cfg, ravello_cache
from . import string_ops as c
from . import ui_methods as ui
try:
    from . import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/blob/ravshello-stable/lib/ravello_sdk.py\n")
    raise

# Set aside globals that will be used for code-clarity
rOpt = user = appnamePrefix = rClient = rCache = rootNode = None

def is_admin():
    if cfg.opts.enableAdminFuncs:
        return True
    else:
        return False


def _complete_path(pathspec):
    """Return filenames to ui_complete_*() methods for path completion."""
    filtered = []
    for entry in glob(path.expanduser(pathspec) + '*'):
        st = stat(entry)
        if pathspec.startswith('~'):
            if pathspec == '~':
                entry = '~'
            elif pathspec.startswith('~/'):
                entry = entry.replace(path.expanduser('~'), '~')
            else:
                tildepath = pathspec.split('/')[0]
                entry = entry.replace(path.expanduser(tildepath), tildepath)
        if S_ISDIR(st.st_mode):
            filtered.append(entry + '/')
        else:
            filtered.append(entry)
    # Put directories at the end
    completions = sorted(filtered, key=lambda i: '~'+i if i.endswith('/') else i)
    if len(completions) == 1 and not completions[0].endswith('/'):
        completions = [completions[0] + ' ']
    return completions


def get_num_learner_active_vms(learner):
    """Return the number of active VMs a learner has."""
    activeVms = 0
    for app in rClient.get_applications(filter={'published': True}):
        if is_admin() and rOpt.showAllApps or app['name'].startswith(appnamePrefix):
            try:
                activeVms += app['deployment']['totalActiveVms']
            except:
                pass
    return activeVms


def launch_directsdk_shell(scriptFile=None, allowScriptedInput=True):
    def p(jsonInput):
        print(json.dumps(jsonInput, indent=4))
    def P(jsonInput):
        pager(json.dumps(jsonInput, indent=4))
    import readline, code
    r = rClient
    R = rCache
    vars = globals().copy()
    vars.update(locals())
    print(dedent("""
        This is a python shell to provide direct access to the Ravello SDK
        See SDK @ https://github.com/ravello/python-sdk/blob/master/lib/ravello_sdk.py
        Objects available for your use:
          r = rClient = ravello_sdk.RavelloClient()
          R = rCache = ravello_cache.RavelloCache()
          c = string_ops
          p(): print(json.dumps(jsonInput, indent=4))
          P(): pager(json.dumps(jsonInput, indent=4))"""), file=stderr)
    shell = code.InteractiveConsole(vars)
    if scriptFile or allowScriptedInput:
        cmds = cfg.opts.cmdlineArgs
        if scriptFile:
            cmds = open(scriptFile).readlines()
        elif cfg.opts.useStdin:
            cmds = stdin.readlines()
        elif cfg.opts.scriptFile:
            cmds = open(cfg.opts.scriptFile).readlines()
        if cmds:
            print(file=stderr)
            for cmd in [line.rstrip('\n') for line in cmds]:
                c.debug("Running python line: {}".format(cmd), file=stderr)
                shell.push(cmd)
            shell.push("")
        if scriptFile or cfg.opts.useStdin or cfg.opts.scriptFile:
            return
    shell.interact("")


def main():
    # Set aside globals that will be used for code-clarity
    global rOpt, user, appnamePrefix, rClient, rCache, rootNode
    rOpt = cfg.opts
    user = cfg.user
    if user:
        appnamePrefix = 'k:{}__'.format(user)
    else:
        appnamePrefix = ''
    rClient = cfg.rClient
    rCache = cfg.rCache
    if rOpt.directsdk:
        launch_directsdk_shell()
        exit()
    # Clear preferences if asked via cmdline arg
    if rOpt.clearPreferences:
        remove(path.join(rOpt.userCfgDir, 'prefs.bin'))
    # Read prefs and override user defaults
    shell = cfshell.ConfigShell(rOpt.userCfgDir)
    shell.prefs['color_mode'] = True
    shell.prefs['tree_max_depth'] = 1
    shell.prefs['prompt_length'] = 0
    shell.prefs['tree_show_root'] = True
    shell.prefs['tree_status_mode'] = True
    shell.prefs['loglevel_console'] = 'info'
    shell.prefs['loglevel_file'] = 'info'
    if rOpt.enableDebugging:
        shell.prefs['loglevel_console'] = 'verbose'
        shell.prefs['loglevel_file'] = 'debug'
    if not c.enableColor:
        shell.prefs['color_mode'] = False
    if not rOpt.showAllApps:
        # Turn off max depth restriction for admins in restricted-view mode
        shell.prefs['tree_max_depth'] = 0
    c.verbose("  Fetching data from Ravello . . . ", end='', file=stderr)
    stdout.flush()
    # Start configshell
    try:
        rootNode = RavelloRoot(shell)
    except:
        print(c.RED("\n  UNHANDLED EXCEPTION getting data from Ravello\n"), file=stderr)
        print("If problem persists, send this message with below traceback to rsaw@redhat.com\n", file=stderr)
        raise
    c.verbose("Done!\n", file=stderr)
    # For some reason sleep is necessary here to fix issue #49
    sleep(0.1)
    if not is_admin():
        try:
            # Plan was to flush sys.stdin with this, per
            # http://abelbeck.wordpress.com/2013/08/29/clear-sys-stdin-buffer/
            # It always throws exception though, so I decided to just use it to quit
            termios.tcflush(stdin, termios.TCIOFLUSH)
        except:
            print(c.red("Sorry! Only admins are allowed to use {} non-interactively\n".format(cfg.prog)))
            exit(1)
        # Initial usage hints
        print(dedent("""\
            {}
             ┐
             │ NAVIGATE: Use `{}` and `{}` with tab-completion
             │ COMMANDS: Use tab-completion to see commands specific to each directory
             │ GET HELP: Use `{}`
             │
             │ Your first time?
             │   - First: use `{}` command
             │   - Next: press TAB-TAB to see available commands
             │   - Next: use `{}` TAB-TAB command to get started
             │   - Optional: `{}` into new app directory and press TAB-TAB to see commands
             │   - Optional: use `{}` command to add an hour to the timer
             └──────────────────────────────────────────────────────────────────────────────
            """
            .format(
                c.BOLD("Instructions:"),
                c.BOLD('cd'), c.BOLD('ls'),
                c.BOLD('help'),
                c.BOLD('cd apps'),
                c.BOLD('new'),
                c.BOLD('cd'),
                c.BOLD('extend_autostop'))), file=stderr)
        shell.run_interactive(exit_on_error=rOpt.enableDebugging)
        return
    if rOpt.useStdin:
        # If stdin was requested, read that in favor of anything else and then exit
        shell.run_stdin(exit_on_error=rOpt.enableDebugging)
        return
    if rOpt.scriptFile:
        # If script was requested, read that in favor of cmdline args and then exit
        shell.run_script(rOpt.scriptFile, exit_on_error=rOpt.enableDebugging)
        return
    # List of commands to run before entering interactive shell
    cmds = []
    # If have preRunCommands from config file, use them to start our list of things to run
    cmds.extend(cfg.cfgFile.get('preRunCommands', []))
    # If have cmdline args, add them to list of things to run
    cmds.extend(rOpt.cmdlineArgs)
    # Run
    for cmd in cmds:
        try:
            shell.run_cmdline(cmd)
        except:
            if rOpt.enableDebugging:
                raise
            else:
                print(c.yellow("Continuing despite error running cmd: '{}'".format(cmd)), file=stderr)
    # If we're still here, enter interactive cmdline
    shell.run_interactive(exit_on_error=rOpt.enableDebugging)


def get_vm_access_details(vm):
    """Get access details about a VM object.
    
    Returns a tuple:
     0) A list of pretty-printable lines (hostnames, IPs, ports, ssh, VNC)
     1) A simple dict of most important details
    """
    out = []
    deets = {'ssh_key': ''}
    sshKey = ""
    if cfg.cfgFile['sshKeyFile']:
        sshKey = " -i {}".format(cfg.cfgFile['sshKeyFile'])
        deets['ssh_key'] = cfg.cfgFile['sshKeyFile']
    # Colorize some things
    if vm['state'] in 'STARTED':
        state = c.GREEN(vm['state'])
    elif vm['state'] in 'STARTING':
        state = c.green(vm['state'])
    elif vm['state'] in 'RESTARTING':
        state = c.magenta(vm['state'])
    elif vm['state'] in 'STOPPING':
        state = c.YELLOW(vm['state'])
    elif vm['state'] in 'STOPPED':
        state = c.yellow(vm['state'])
    elif vm['state'] in 'PUBLISHING':
        state = c.red(vm['state'])
    else:
        state = c.RED(vm['state'])
    # Print state and hostnames
    out.append("{}".format(c.BOLD(vm['name'])))
    out.append("   State:            {}".format(state))
    if 'hostnames' in vm:
        out.append("   Hostnames:        {}".format(", ".join(vm['hostnames'])))
    # Setup empty ssh dict
    vm['ssh'] = {'port': '', 'fqdn': ''}
    nics = []
    # Compile and print details on each network interface
    for nic in vm.get('networkConnections', []):
        n = {'name': nic['name'], 'publicIP': '', 'publicIPtype': ''}
        internal = None
        ip_Additional = []
        fqdn = ''
        ip_Elastic = None
        ip_Public = None
        ip_Forwarder = None
        services = []
        # Get private IPs
        if 'autoIpConfig' in nic['ipConfig']:
            internal = nic['ipConfig']['autoIpConfig']['allocatedIp']
        elif 'staticIpConfig' in nic['ipConfig']:
            internal = nic['ipConfig']['staticIpConfig']['ip']
        n['internalIP'] = internal
        # Get extra private IPs
        for addtlIp in nic.get('additionalIpConfig', []):
            ip_Additional.append(addtlIp['staticIpConfig']['ip'])
        n['internalIPs'] = ip_Additional
        # Get FQDN
        if 'fqdn' in nic['ipConfig']:
            fqdn = nic['ipConfig']['fqdn']
        n['fqdn'] = fqdn
        # Get public IP
        if nic['ipConfig']['hasPublicIp']:
            try:
                ip_Elastic = nic['ipConfig']['elasticIpAddress']
            except:
                try:
                    ip_Public = nic['ipConfig']['publicIp']
                except:
                    pass
        elif 'publicIp' in nic['ipConfig']:
            ip_Forwarder = nic['ipConfig']['publicIp']
        # Check for services
        for svc in vm.get('suppliedServices', []):
            if svc['external'] and 'externalPort' in svc and svc['useLuidForIpConfig'] and nic['ipConfig']['id'] == svc['ipConfigLuid'] and not svc['name'].startswith('dummy'):
                services.append(svc)
                if svc['name'] == 'ssh' and not vm['ssh']['fqdn']:
                    vm['ssh']['fqdn'] = deets['ssh_fqdn'] = fqdn
                    deets['ssh_port'] = svc['externalPort']
                    if svc['externalPort'] != "22":
                        vm['ssh']['port'] = " -p {}".format(svc['externalPort'])
        n['services'] = services
        # Finally, print:
        out.append("   NIC {}".format(nic['name']))
        out.append("     Internal IP:    {}".format(internal))
        for ip in ip_Additional:
            out.append("     Internal IP:    {}".format(ip))
        if ip_Elastic:
            out.append("     PubIP Elastic:  {} ({})".format(ip_Elastic, fqdn))
            n['publicIP'] = ip_Elastic
            n['publicIPtype'] = 'elastic'
        elif ip_Public:
            out.append("     PubIP Static:   {} ({})".format(ip_Public, fqdn))
            n['publicIP'] = ip_Public
            n['publicIPtype'] = 'static'
        elif ip_Forwarder and services:
            out.append("     PubIP DNAT:     {} ({})".format(ip_Forwarder, fqdn))
            n['publicIP'] = ip_Forwarder
            n['publicIPtype'] = 'forwarding'
        for svc in services:
            s = "{svc} port {exPort}/{proto} maps to internal port {inPort}".format(
                svc=svc['name'],
                exPort=svc['externalPort'],
                proto=svc['protocol'],
                inPort=svc['portRange'])
            out.append("     External Svc:   {}".format(s))
        nics.append(n)
    deets['nics'] = nics
    if vm['state'] in ['STARTING', 'STARTED']:
        # Print ssh command
        if vm['ssh']['fqdn']:
            ssh = c.cyan("ssh{}{} root@{}".format(sshKey, vm['ssh']['port'], vm['ssh']['fqdn']))
            out.append("   SSH Command:      {}".format(ssh))
    vnc = ''
    if vm['state'] in ['STARTED']:
        try:
            vnc = rClient.get_vnc_url(vm['applicationId'], vm['id'])
        except:
            pass
        else:
            # Print VNC url
            out.append("   VNC Web URL:      {}".format(c.blue(vnc)))
    deets['vnc'] = vnc
    return out, deets


class RavelloRoot(ConfigNode):
    """Setup the Ravello root node where anything is possible.
    
    Path: /
    """
    
    def __init__(self, shell):
        ConfigNode.__init__(self, '/', shell=shell)
        Applications(self)
        if is_admin():
            Blueprints(self)
            Billing(self)
            Users(self)
            Monitoring(self)
            Events(self)
            # Images(self)
            Shared(self)
            Keypairs(self)
        else:
            self.ui_command_directsdk_shell = None
    
    def summary(self):
        if is_admin():
            status = "Local admin user: {}, Ravello user: {}".format(user, rClient._username)
        else:
            status = "Logged in as user: {}".format(user)
        return (status, None)
    
    def ui_command_directsdk_shell(self, inputFile='@console'):
        """
        Launch interactive python shell to run raw SDK queries or debug ravshello.
        
        Objects available in this shell:
          r = rClient = ravello_sdk.RavelloClient()
          R = rCache = ravello_cache.RavelloCache()
          c = string_ops
          p(): print(json.dumps(jsonInput, indent=4))
          P(): pager(json.dumps(jsonInput, indent=4))
        
        For help on the SDK, execute help(r) from the shell or consult:
        https://github.com/ravello/python-sdk/blob/master/lib/ravello_sdk.py
        
        If *inputFile* is anything other than '@console', it should be a file
        containing python code to be run in the current environment.
        
        Note that this shell can also be entered from the OS command-line by
        use of the -D or --directsdk options.
        """
        inputFile = self.ui_eval_param(inputFile, 'string', '@console')
        if inputFile == '@console':
            inputFile = None
        launch_directsdk_shell(scriptFile=inputFile, allowScriptedInput=False)
    
    def ui_complete_directsdk_shell(self, parameters, text, current_param):
        if current_param in ['inputFile']:
            return _complete_path(text)
        else:
            return []


class Events(ConfigNode):
    """Setup the 'events' node.
    
    Path: /events/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'events', parent)
        self.isPopulated = False
    
    def summary(self):
        if self.isPopulated:
            return ("Alerts registered for {} of {} possible events".format(self.numberOfRegisteredEvents, self.numberOfEvents), None)
        else:
            return ("To populate, run: refresh", False)
        
    def refresh(self):
        self._children = set([])
        rCache.update_user_cache()
        self.numberOfEvents = self.numberOfRegisteredEvents = 0
        for eventName in rClient.get_events():
            Event("%s" % eventName.swapcase(), self)
        self.isPopulated = True
    
    def ui_command_refresh(self):
        """
        Poll Ravello for list of event names and registered userAlerts.
        
        Not doing this automatically speeds startup time.
        """
        print(c.yellow("\nRefreshing all event & userAlert data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))
    
    def print_event_names(self):
        pager("JSON list of EVENT NAMES\n" +
              ui.prettify_json(rClient.get_events()))
    
    def ui_command_print_event_names(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON list of Ravello event names.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        
        Alerts can be registered for any of the returned event names with the
        register command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "list of event names"
        ui.print_obj(rClient.get_events(), description, outputFile, tmpPrefix='events')
    
    def ui_complete_print_event_names(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []
    
    def ui_command_print_registered_alerts(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON list of registered userAlerts.
        
        Assuming the current Ravello user is an admin, they will actually see
        all alerts in the organization.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        
        Create alerts with the register command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "list of registered userAlerts"
        ui.print_obj(rClient.get_alerts(), description, outputFile, tmpPrefix='alerts')
    
    def ui_complete_print_registered_alerts(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []


class Event(ConfigNode):
    """Setup the dynamically-named event node.
    
    Path: /events/{EVENT_NAME}/
    """
    
    def __init__(self, eventName, parent):
        ConfigNode.__init__(self, eventName, parent)
        parent.numberOfEvents += 1
        self.eventName = eventName.swapcase()
        self.refresh()
    
    def refresh(self):
        self._children = set([])
        eventAlerts = rCache.get_alerts_for_event(self.eventName)
        if eventAlerts:
            self.parent.numberOfRegisteredEvents += 1
            for a in eventAlerts:
                user = c.replace_bad_chars_with_underscores(rCache.get_user(a['userId'])['email'])
                UserAlert(user, self, a['alertId'], a['userId'])
    
    def summary(self):
        eventAlerts = rCache.get_alerts_for_event(self.eventName)
        if eventAlerts:
            return ("Alerts registered", True)
        else:
            return ("No alerts", False)
    
    def ui_command_register(self, userEmail='@moi'):
        """
        Register currently logged-in Ravello user to receive email on event.
        
        Assuming currently logged in Ravello user is an admin, you can specify
        the user to register via the userEmail option. Note that you cannot
        enter an arbitrary email address; it must be the email of an existing
        Ravello user (see /users).
        """
        print()
        userEmail = self.ui_eval_param(userEmail, 'string', '@moi')
        if userEmail == '@moi':
            userId = None
        else:
            # The following conditionally updates the cache and returns None
            rCache.get_user()
            for userId in rCache.userCache:
                if not userId == '_timestamp' and rCache.userCache[userId]['email'] == userEmail:
                    break
            else:
                print(c.RED("No Ravello user on your account with that email!\n"))
                return
        print(c.yellow("Attempting to register alert . . . "), end='')
        stdout.flush()
        try:
            rClient.create_alert(self.eventName, userId)
        except:
            print(c.red("\n\nProblem registering alert!\n"))
            raise
        print(c.green("DONE!\n"))
        rCache.purge_alert_cache()
        self.refresh()
    
    def ui_complete_register(self, parameters, text, current_param):
        if current_param == 'userEmail':
            rCache.get_user()
            L = []
            for userId in rCache.userCache:
                if not userId == '_timestamp':
                    L.append(rCache.userCache[userId]['email'])
            completions = [a for a in L
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions


class UserAlert(ConfigNode):
    """Setup the dynamically-named user alert node.
    
    Path: /events/{EVENT_NAME}/{USER_EMAIL}/
    """
    
    def __init__(self, userString, parent, alertId, userId):
        ConfigNode.__init__(self, userString, parent)
        self.userId = userId
        self.alertId = alertId
        self.refresh()
    
    def refresh(self):
        self._timestamp = time()
        u = rCache.get_user(self.userId)
        if u:
            self.status = "{} {}; {}; UID {}".format(
                u['name'], u['surname'], u['email'], u['id'])
        else:
            self.status = None
    
    def summary(self):
        if ui.get_timestamp_proximity(self._timestamp) < -120:
            self.refresh()
        return (self.status, None)
    
    def ui_command_unregister(self):
        """
        Delete a previously-registered alert.
        """
        print()
        print(c.yellow("Attempting to unregister alert . . . "), end='')
        stdout.flush()
        try:
            rClient.delete_alert(self.alertId)
        except:
            print(c.red("\n\nProblem unregistering alert!\n"))
            raise
        print(c.green("DONE!\n"))
        rCache.purge_alert_cache()
        self.parent.remove_child(self)


class Monitoring(ConfigNode):
    """Setup the 'monitoring' node.
    
    Path: /monitoring/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'monitoring', parent)
    
    def summary(self):
        return ("Ready for queries", None)
    
    def daily_activity_summary(self, output='@stdout', day=date.today().day,
            month=date.today().month, year=date.today().year):
        """Print a report of account activity for the current day.
        
        Optionally specify output as @stdout or @pager or <FilePath>.
        The day, month, and year must all be specified as absolute (positive)
        numbers.
        """
        print()
        output = self.ui_eval_param(output, 'string', '@stdout')
        day = self.ui_eval_param(month, 'number', date.today().day)
        month = self.ui_eval_param(month, 'number', date.today().month)
        year = self.ui_eval_param(year, 'number', date.today().year)
        if day < 1 or day > 31:
            print(c.RED("Invalid day specification!\n"))
            return
        if month < 1 or month > 12:
            print(c.RED("Invalid month specification!\n"))
            return
        if year < 2010 or year > 2037:
            print(c.RED("Invalid year specification!\n"))
            return
    
    def ui_command_search_notifications(self, appId=None, maxResults=500,
            notificationLevel=None, startTime=None, endTime=None,
            outputFile='@EDITOR'):
        """
        Pretty-print JSON list of notification search results.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        
        Results will be returned in reverse chronological order with
        newest matches at the top.
        
        To see details about a specific application only, determine appId first,
        e.g., with print_def command.
        
        To remove limit on number of results, set maxResults=0.
        
        To restrict results by type, set notificationLevel=INFO (or WARN, ERROR).
        By default notificationLevel is set to None which means all levels are
        shown. DEV NOTE: There might be other levels; I've only seen those 3.
        
        startTime and endTime must be provided in UNIX time format, e.g.,
        specifying 1375367161 would result in a date of Aug 1 14:26:01 UTC 2013.
        Register an RFE if you're interested in specifying it differently (e.g.,
        perhaps an interactive prompt).
        
        NOTE TO DEVELOPERS:
        Per the API (e.g., see ravellosystems.com/developers/rest-api/notifications)
        Ravello always does times in a non-standard way, where the thousandths
        of a second are always present, but there's no delimiting decimal place,
        as is customary. ...
        This function compensates for you by appending 3 zeroes to the end of any
        number you pass (so basically, don't worry about it).
        """
        #### FIXME: This could be made waaaaay more friendly and useful.
        print()
        maxResults = self.ui_eval_param(maxResults, 'number', 500)
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        #~ appId = self.ui_eval_param(appId, 'number', None)
        #~ notificationLevel = self.ui_eval_param(notificationLevel, 'string', 'INFO')
        if isinstance(startTime, int): startTime=int(str(startTime) + '000')
        if isinstance(endTime, int): endTime=int(str(endTime) + '000')
        req = {'maxResults': maxResults, 'appId': appId,
               'notificationLevel': notificationLevel,
               'dateRange': {'startTime': startTime, 'endTime': endTime}}
        description = "list of notification search results"
        ui.print_obj(rClient.search_notifications(req), description, outputFile,
            tmpPrefix='notifications')
    
    # FIXME: Add ui_complete_search_notifications()


class Billing(ConfigNode):
    """Setup the 'billing' node.
    
    Path: /billing/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'billing', parent)
    
    def summary(self):
        return ("Ready for queries", None)
    
    def validate_or_prompt_for_month(self, month, year):
        if month == '@prompt':
            x = ui.monthdelta(date.today(), -1)
            month = x.month
            year = x.year
            month = ui.prompt_for_number(
                c.CYAN("Enter month by number [{}]: ".format(month)),
                startRange=1, endRange=12, defaultNumber=month)
            print()
        else:
            try:
                month = int(month)
                if month == 0:
                    month = date.today().month
                elif month < 0:
                    x = ui.monthdelta(date.today(), month)
                    month = x.month
                    year = x.year
            except:
                print(c.RED("Invalid month specification!\n"))
                raise
        return month, year
    
    def ui_command_inspect_all_charges(self, month='@prompt',
            year=date.today().year, outputFile='@EDITOR'):
        """
        Print full JSON for all charges in a specific month.
        
        Optionally specify *month* to avoid being prompted.
        Setting *month* to 0 is the same as specifying the number of the current
        month. Specifying a negative number for *month* will cause *year*
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The *year* can only be specified as an absolute (positive) number.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        month = self.ui_eval_param(month, 'string', '@prompt')
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        year = self.ui_eval_param(year, 'number', date.today().year)
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
        when = "{}-{}".format(year, month_name[month][:3])
        print(c.yellow("Pulling summary of charges for {} . . .\n".format(when)))
        try:
            billing = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        description = "details of all charges incurred during month {}".format(when)
        ui.print_obj(billing, description, outputFile,
            tmpPrefix='billing_{}'.format(month_name[month][:3]))
    
    def _complete_file_month_year(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param == 'month':
            L = map(str, range(-12, 13))
            L.insert(0, '@prompt')
            completions = [a for a in L
                           if a.startswith(text)]
        elif current_param == 'year':
            L = map(str, range(2013, date.today().year + 1))
            completions = [a for a in L
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
            
    def ui_complete_inspect_all_charges(self, parameters, text, current_param):
        return self._complete_file_month_year(parameters, text, current_param)
    
    def _complete_file_month_year_sortby(self, parameters, text, current_param):
        completions = self._complete_file_month_year(parameters, text, current_param)
        if current_param == 'sortBy':
            completions = [a for a in ['nick', 'user']
                           if a.startswith(text)]
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_export_month_to_csv(self, month='@prompt',
            year=date.today().year, sortBy='nick', outputFile='@EDITOR'):
        """
        Export per-app details of a particular month in CSV format.
        
        Optionally specify *month* to avoid being prompted.
        Setting *month* to 0 is the same as specifying the number of the
        current month. Specifying a negative number for *month* will cause year
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The *year* can only be specified as an absolute (positive) number.

        With *sortBy*, charges can be sorted by Ravello user login ('user') or
        ravshello nickname ('nick').
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        month = self.ui_eval_param(month, 'string', '@prompt')
        year = self.ui_eval_param(year, 'number', date.today().year)
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
        sortBy = self.ui_eval_param(sortBy, 'string', 'nick')
        if not sortBy == 'user' and not sortBy == 'nick':
            print(c.RED("Specify sortBy as 'user' or 'nick'\n"))
            return
        when = "{}-{}".format(year, month_name[month][:3])
        print(c.yellow("Pulling summary of charges for {} . . .\n".format(when)))
        try:
            billing = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        csv = self.gen_csv(b, sortBy)
        description = "CSV details of all charges incurred during month {}".format(when)
        ui.print_obj(billing, description, outputFile,
            tmpPrefix='billing_{}'.format(month_name[month][:3]), suffix='.csv')
    
    def ui_complete_export_month_to_csv(self, parameters, text, current_param):
        return self._complete_file_month_year_sortby(parameters, text, current_param)
    
    def ui_command_this_months_summary(self, sortBy='nick', outputFile='@pager'):
        """
        Print billing summary of all charges since beginning of this month.
        
        With *sortBy*, charges can be sorted by Ravello user login ('user') or
        ravshello nickname ('nick').
        
        Optionally specify *outputFile* as @term or @EDITOR or as a relative /
        absolute path on the local system (tab-completion available). When
        writing out to files, it might be helpful to use ravshello --nocolor.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        sortBy = self.ui_eval_param(sortBy, 'string', 'nick')
        if not sortBy == 'user' and not sortBy == 'nick':
            print(c.RED("Specify sortBy as 'user' or 'nick'\n"))
            return
        print("Warning: data could be up to 1 hour old")
        print(c.yellow("Pulling summary of charges since the start of this month . . .\n"))
        try:
            billing = rClient.get_billing()
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        txt = self.gen_txt_summary(billing, sortBy)
        description = "billing summary of charges incurred since the start of this month"
        ui.print_obj(txt, description, outputFile,
            tmpPrefix='billing_thismonth', suffix='.txt')
    
    def ui_complete_this_months_summary(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param == 'sortBy':
            completions = [a for a in ['nick', 'user']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_select_month_summary(self, month='@prompt',
        year=date.today().year, sortBy='nick', outputFile='@pager'):
        """
        Print billing summary of all charges in a specific month.
        
        Setting *month* to 0 is the same as specifying the number of the current
        month. Specifying a negative number for *month* will cause *year*
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The *year* can only be specified as an absolute (positive) number.
        
        With *sortBy*, charges can be sorted by Ravello user login ('user') or
        ravshello nickname ('nick').
        
        Optionally specify *outputFile* as @term or @EDITOR or as a relative /
        absolute path on the local system (tab-completion available). When
        writing out to files, it might be helpful to use ravshello --nocolor.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        month = self.ui_eval_param(month, 'string', '@prompt')
        year = self.ui_eval_param(year, 'number', date.today().year)
        sortBy = self.ui_eval_param(sortBy, 'string', 'nick')
        if not sortBy == 'user' and not sortBy == 'nick':
            print(c.RED("Specify sortBy as 'user' or 'nick'\n"))
            return
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
        when = "{}-{}".format(year, month_name[month][:3])
        print(c.yellow("Pulling summary of charges for {} . . .\n".format(when)))
        try:
            billing = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        txt = self.gen_txt_summary(billing, sortBy)
        description = "billing summary of charges incurred during month {}".format(when)
        ui.print_obj(txt, description, outputFile,
            tmpPrefix='billing_{}'.format(month_name[month][:3]), suffix='.txt')
    
    def ui_complete_select_month_summary(self, parameters, text, current_param):
        return self._complete_file_month_year_sortby(parameters, text, current_param)
    
    def _process_billing_input(self, monthsCharges, sortBy):
        """Crunch the numbers on list returned by RavelloClient.get_billing()
        
        Return 2 dictionaries which can be used by gen_txt_summary() or gen_csv().
        """
        appsByUser = {}
        chargesByProduct = {}
        for app in monthsCharges:
            try:
                appName = app['appName']
            except:
                appName = "UNDEFINED"
            try:
                upTime = app['upTime']
            except:
                upTime = None
            if sortBy == 'nick':
                if appName.startswith('k:'):
                    user, appName = appName.split('__', 1)
                    user = user.split(':')[1]
                else:
                    user = "APPS THAT DON'T FOLLOW NICKNAME NAMING SCHEME"
            else:
                try:
                    user = app['owner']
                except:
                    user = "ORG (not associated with specific apps)"
            if user not in appsByUser:
                appsByUser[user] = []
            totalCharges = 0.0
            unitHours = 0.0
            for product in app['charges']:
                try:
                    m = re.search('hour', product['unitName'], re.IGNORECASE)
                    if m:
                        unitHours += product['productCount']
                except:
                    pass
                try:
                    totalCharges += product['summaryPrice']
                except:
                    pass
                prodName = product['productName'].replace('Performance Opt', 'Perf-Opt').replace('Cost Opt', 'Cost-Opt')
                if prodName not in chargesByProduct:
                    chargesByProduct[prodName] = {
                        'summaryPrice': 0.0,
                        'productCount': 0.0,
                        'productRate': product['productRate'],
                        'unitName': product['unitName'],
                        }
                chargesByProduct[prodName]['summaryPrice'] += product['summaryPrice']
                chargesByProduct[prodName]['productCount'] += product['productCount']
            try:
                creationTime = int(str(app['creationTime'])[:-3])
            except:
                creationTime = 0
            appsByUser[user].append({
                'appName': appName,
                'unitHours': unitHours,
                'upTime': upTime,
                'totalCharges': totalCharges,
                'creationTime': creationTime,
                })
        return appsByUser, chargesByProduct
    
    def gen_csv(self, monthsCharges, sortBy):
        """Generate CSV-formatted output of billing info."""
        appsByUser, chargesByProduct = self._process_billing_input(monthsCharges, sortBy)
        out = [
            "User,App Name,Unit Hours,Up Time Hours,App Charges"
            ]
        for user in appsByUser:
            for app in sorted(appsByUser[user], key=itemgetter('creationTime')):
                out.append("{},{},{},{},{}".format(
                    user, app['appName'], app['unitHours'], app['upTime'], app['totalCharges']))
        return "\n".join(out)
 
    def gen_txt_summary(self, monthsCharges, sortBy):
        """Generate billing goodness with pretty colors."""
        out = []
        appsByUser, chargesByProduct = self._process_billing_input(monthsCharges, sortBy)
        acctGrandTotal = 0
        for user in appsByUser:
            userTotalHoursUptime = 0
            userGrandTotalCharges = 0.0
            out.append(c.BLUE("{}:".format(user)))
            out.append(c.magenta("    Charges\tHours\tCreation Time\tApplication Name"))
            for app in sorted(appsByUser[user], key=itemgetter('creationTime')):
                tc = app['totalCharges']
                userGrandTotalCharges += tc
                if tc < 5:
                    tc = c.green("${:8.2f}".format(tc))
                elif tc < 15:
                    tc = c.yellow("${:8.2f}".format(tc))
                elif tc < 25:
                    tc = c.YELLOW("${:8.2f}".format(tc))
                elif tc < 35:
                    tc = c.red("${:8.2f}".format(tc))
                else:
                    tc = c.RED("${:8.2f}".format(tc))
                if not app['creationTime']:
                    creationTime = "N/A\t"
                else:
                    creationTime = datetime.fromtimestamp(
                        app['creationTime']).strftime('%m/%d @ %H:%M')
                if app['upTime'] is not None:
                    userTotalHoursUptime += app['upTime']
                    upTime = "{}".format(app['upTime'])
                else:
                    upTime = "N/A"
                out.append("    {}\t{}\t{}\t{}"
                           .format(tc, upTime, creationTime, app['appName']))
            acctGrandTotal += userGrandTotalCharges
            if not app['totalCharges'] == userGrandTotalCharges:
                out.append("    -----------------")
                out.append("    " +
                           c.REVERSE("${:8.2f}\t{:g}"
                                     .format(userGrandTotalCharges, userTotalHoursUptime)))
            out.append("")
        prodGrandTotal = 0
        out.append("")
        out.append(c.BLUE("Charges by product:"))
        out.append(c.magenta("    Charges      Unit Price                Count           Product Name"))
        for product in sorted(chargesByProduct):
            tc = chargesByProduct[product]['summaryPrice']
            prodGrandTotal += tc
            if tc < 15:
                tc = c.green("${:9.2f}".format(tc))
            elif tc < 50:
                tc = c.yellow("${:9.2f}".format(tc))
            elif tc < 90:
                tc = c.YELLOW("${:9.2f}".format(tc))
            elif tc < 130:
                tc = c.red("${:9.2f}".format(tc))
            else:
                tc = c.RED("${:9.2f}".format(tc))
            out.append(
                "    {sumcharges}   ${unitprice:.2f} {unit:20}{count:<16.1f}{name}"
                .format(
                    sumcharges=tc,
                    unitprice=chargesByProduct[product]['productRate'],
                    unit=chargesByProduct[product]['unitName'].replace('Hour', 'Hr'),
                    count=chargesByProduct[product]['productCount'],
                    name=product))
        out.append("    ----------")
        out.append(
            "    "  +
            c.REVERSE("${:9.2f}   Monthly charges grand total".format(prodGrandTotal)))
        out.append("")
        return "\n".join(out)


class Users(ConfigNode):
    """Setup the 'users' node.
    
    Path: /users/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'users', parent)
        self.isPopulated = False
    
    def summary(self):
        if self.isPopulated:
            return ("{} admins, {} users".format(self.numberOfAdmins, self.numberOfUsers - self.numberOfAdmins), None)
        else:
            return ("To populate, run: refresh", False)
    
    def refresh(self):
        self._children = set([])
        self.numberOfUsers = self.numberOfAdmins = 0
        for user in rCache.get_users():
            User(c.replace_bad_chars_with_underscores(user['email']), self, user['id'])
            if 'ADMIN' in user['roles']:
                self.numberOfAdmins += 1
        self.isPopulated = True
    
    def ui_command_refresh(self):
        """
        Poll Ravello for user list.
        
        There are a few situations where this might come in handy:
            - If you create or delete users in the Ravello web UI
            - If you delete users in a separate instance of ravshello
            - If you create or delete users via the API using some other means
        """
        print(c.yellow("\nRefreshing all user data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))
    
    def ui_command_invite(self):
        """
        Create new user account via invitation.
        
        There apears to be a bug in the Ravello API. This doesn't work.
        """
        print("\nEnter details of new user you'd like to invite . . .")
        req = {}
        req['email'] = raw_input(c.CYAN("\nEmail: "))
        req['name'] = raw_input(c.CYAN("\nFirst name: "))
        req['surname'] = raw_input(c.CYAN("\nLast name: "))
        print()
        try:
            user = rClient.create_user(req)
        except:
            print(c.red("Problem inviting user\n!"))
            raise
        print(c.green("Invited user {}\n".format(req['email'])))
        User("%s" % user['email'], self, user['id'])


class User(ConfigNode):
    """Setup the dynamically-named user node.
    
    Path: /users/{USER_EMAIL}/
    """
    
    def __init__(self, user, parent, userId):
        ConfigNode.__init__(self, user, parent)
        parent.numberOfUsers += 1
        self.user = user
        self.userId = userId
        self.refresh()
    
    def refresh(self):
        self._timestamp = time()
        u = rCache.get_user(self.userId)
        if u['locked'] or not (u['activated'] and u['enabled']):
            self.happy = False
        elif 'ADMIN' in u['roles']:
            self.happy = True
        else:
            self.happy = None
        self.status = "{} {}; {}; UID {}".format(
            u['name'], u['surname'], u['email'], u['id'])
    
    def summary(self):
        if ui.get_timestamp_proximity(self._timestamp) < -120:
            self.refresh()
        return (self.status, self.happy)
    
    def ui_command_print_def(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON definition of user details.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "user definition for /users/{}".format(self.user)
        ui.print_obj(rCache.get_user(self.userId), description, outputFile,
            tmpPrefix='user_{}'.format(self.user))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []
    
    def ui_command_update_info(self):
        """
        Update user first/last name and admin status.
        """
        user = rClient.get_user(self.userId)
        print("\nNote that only name and roles can be updated")
        name = raw_input(c.CYAN("\nEnter first name [{}]: ".format(user['name'])))
        if not name:
            name = user['name']
        surname = raw_input(c.CYAN("\nEnter last name [{}]: ".format(user['surname'])))
        if not surname:
            surname = user['surname']
        minusAdmin = addAdmin = False
        if 'ADMIN' in user['roles']:
            response = raw_input(c.CYAN("\nRevoke user's admin access? [y/N] "))
            if response == 'y':
                user['roles'] = ['USER']
                minusAdmin = True
        else:
            response = raw_input(c.CYAN("\nGive user admin access? [Y/n] "))
            if response == 'n':
                pass
            else:
                user['roles'].append('ADMIN')
                addAdmin = True
        print()
        # Create request dictionary
        req = {
            'email': user['email'],
            'name': name,
            'surname': surname,
            'roles': user['roles'],
            }
        try:
            rCache.userCache[user['id']] = rClient.update_user(req, user['id'])
        except:
            print(c.red("Problem updating user!\n"))
            raise
        if minusAdmin:
            self.parent.numberOfAdmins -= 1
        elif addAdmin:
            self.parent.numberOfAdmins += 1
        print(c.green("Updated user info\n"))
    
    def ui_command_delete(self):
        """
        Delete a user.
        
        Hopefully very carefully. No option to bypass confirmation for this one.
        """
        print()
        userEmail = rCache.get_user(self.userId)['email']
        c.slow_print(c.bgRED("  W A R N I N G ! ! ! !"))
        c.slow_print(c.RED("\nPress Ctrl-c now unless you are ABSOLUTELY SURE you want to delete {}'s account!"
                         .format(userEmail)))
        c.slow_print(c.RED("ARE YOU POSITIVELY CONFIDENT THAT ALL THIS USER'S APPS & VMS SHOULD BE DESTROYED?"))
        response = raw_input(c.CYAN("\nType 'yes!' in ALL CAPS to continue: "))
        print()
        if response == 'YES!':
            if 'ADMIN' in rCache.get_user(self.userId)['roles']:
                admin = True
            else:
                admin = False
            try:
                rClient.delete_user(self.userId)
            except:
                print(c.red("Problem deleting user!\n"))
                raise
            self.parent.numberOfUsers -= 1
            if admin:
                self.parent.numberOfAdmins -= 1
            print(c.green("Deleted user {}\n".format(userEmail)))
            self.parent.remove_child(self)
        else:
            print("Leaving user intact (probably a good choice)\n")
    
    def ui_command_change_password(self):
        """
        Change a user's password.
        
        Doing this requires entering the current password.
        """
        userEmail = rCache.get_user(self.userId)['email']
        req = {}
        req['existingPassword'] = ui.get_passphrase(c.CYAN("\nEnter {}'s current password: ".format(userEmail)))
        print()
        req['newPassword'] = ui.get_passphrase(c.CYAN("Enter new password: "), confirm=True)
        print()
        try:
            rClient.changepw_user(req, self.userId)
        except:
            print(c.red("Problem changing user password!\n"))
            raise
        print(c.green("Updated user password\n"))


class Blueprints(ConfigNode):
    """Setup the 'blueprints' node.
    
    Path: /blueprints/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'blueprints', parent)
        self.isPopulated = False
    
    def summary(self):
        if self.isPopulated:
            learners = ""
            if self.numberOfLearnerBps:
                learners = ", {} tagged for learners".format(self.numberOfLearnerBps)
            return ("{} blueprints{}".format(self.numberOfBps, learners), None)
        else:
            return ("To populate, run: refresh", False)
    
    def refresh(self):
        rCache.update_bp_cache()
        self._children = set([])
        sharedWithMe = SharedBps(self)
        self.numberOfBps = self.numberOfLearnerBps = 0
        for bp in rCache.get_bps():
            if rCache.get_user(bp['ownerDetails']['userId']):
                Bp(bp, self)
            else:
                Bp(bp, sharedWithMe)
        self.isPopulated = True
    
    def ui_command_refresh(self):
        """
        Poll Ravello for blueprint list.
        
        There are a few situations where this might come in handy:
            - If you create or delete blueprints in the Ravello web UI
            - If you create or delete bps in a separate instance of ravshello
            - If you create or delete bps via the API using some other means
        """
        print(c.yellow("\nRefreshing all blueprint data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))


class SharedBps(ConfigNode):
    """Setup the 'Shared_with_me' node.
    
    Path: /blueprints/Shared_with_me
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'Shared_with_me', parent)
        self.numberOfBps = self.numberOfLearnerBps = 0
    
    def summary(self):
        return ("{} blueprints shared with me".format(self.numberOfBps), None)


class Bp(ConfigNode):
    """Setup the dynamically-named blueprint node.
    
    Path: /blueprints/{BLUEPRINT_NAME}/
    """
    def __init__(self, bp, parent):
        ConfigNode.__init__(self, bp['name'], parent)
        parent.numberOfBps += 1
        self.bp = bp
        self.bpName = bp['name']
        self.bpId = bp['id']
        self.bpOwner = bp['owner']
        self.creationTime = datetime.fromtimestamp(int(str(bp['creationTime'])[:-3]))
        if 'description' in bp and any(tag in bp['description'] for tag in cfg.learnerBlueprintTag):
            self.isLearnerBp = True
            parent.numberOfLearnerBps += 1
        else:
            self.isLearnerBp = False
        if parent != rootNode.get_child('blueprints'):
            # If we are a shared blueprint
            self.ui_command_delete = None
            self.ui_command_find_pub_locations = None
    
    def summary(self):
        if self.creationTime.year == datetime.now().year:
            if (self.creationTime.month == datetime.now().month and
                self.creationTime.day == datetime.now().day):
                    created = self.creationTime.strftime('today @ %H:%M')
            else:
                created = self.creationTime.strftime('%m/%d')
        else:
            created = self.creationTime.strftime('%Y/%m/%d')
        if self.isLearnerBp:
            happy = True
        else:
            happy = None
        return ("{} created {}".format(self.bpOwner, created), happy)
    
    def delete(self):
        try:
            rClient.delete_blueprint(self.bpId)
        except:
            print(c.red("Problem deleting blueprint!\n"))
            raise
        print(c.green("Deleted blueprint {}\n".format(self.bpName)))
        self.parent.remove_child(self)
        self.parent.numberOfBps -= 1
    
    def ui_command_delete(self, noconfirm='false'):
        """
        Delete a blueprint.
        
        By default, confirmation will be required to delete the blueprint.
        Disable prompt with noconfirm=true.
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        print()
        if not noconfirm:
            c.slow_print(c.RED("Deleting a blueprint cannot be undone -- make sure you know what you're doing\n"))
            response = raw_input(c.CYAN("Continue with blueprint deletion? [y/N] "))
            print()
        if noconfirm or response == 'y':
            self.delete()
        else:
            print("Leaving bp intact (probably a good choice)\n")
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param in ['noconfirm']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_find_pub_locations(self, outputFile='@EDITOR'):
        """
        Print details about available publish locations for a blueprint.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "BP available publish locations for /blueprints/{}".format(self.bpName)
        ui.print_obj(rClient.get_blueprint_publish_locations(self.bpId),
            description, outputFile, tmpPrefix='publoc_{}'.format(self.bpName))
    
    def ui_command_print_def(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON definition of blueprint.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        if self.parent == rootNode.get_child('blueprints'):
            bpPath = "/blueprints/{}".format(self.bpName)
        else:
            bpPath = "/blueprints/Shared_with_me/{}".format(self.bpName)
        description = "BP definition for {}".format(bpPath)
        ui.print_obj(rClient.get_blueprint(self.bpId), description, outputFile,
            tmpPrefix='bp_{}'.format(self.bpName))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []
    
    def ui_command_copy(self, name='@prompt', desc='@prompt'):
        """
        Create a copy of an existing blueprint.
        
        Optionally specify *name* and/or *desc* on the command-line to avoid
        prompting (both default to '@prompt' and both can be set to '@auto'
        to skip prompting).
        """
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        newBpDescription = "Created by {} as a copy of blueprint '{}'".format(user, self.bpName)
        # Prompt for a blueprint name if necessary
        if name == '@prompt':
            b = raw_input(c.CYAN("\nEnter a unique name for your new blueprint [{}]: ".format(self.bpName)))
            if len(b):
                newBpName = b
            else:
                newBpName = self.bpName
        elif name == '@auto':
            newBpName = ravello_sdk.new_name(rCache.get_bps(myOrgOnly=True), self.bpName + '_')
        else:
            newBpName = name
        # Prompt for description if necessary
        if desc == '@prompt':
            d = raw_input(c.CYAN("\nOptionally enter a description for your new blueprint [{}]: ".format(newBpDescription)))
            if len(d):
                newBpDescription = d
        elif desc == '@auto':
            pass
        else:
            newBpDescription = desc
        # Create request dictionary and post new bp
        req = {
            "blueprintId": self.bpId,
            "blueprintName": newBpName,
            "description": newBpDescription,
            "offline": True,
            }
        try:
            newBp = rClient.create_blueprint(req)
        except:
            print(c.red("\nProblem creating new blueprint!\n"))
            raise
        print(c.green("\nSUCCESS! New blueprint '{}' created!".format(newBpName)))
        # Add new bp to directory tree
        Bp(newBp, rootNode.get_child('blueprints'))
        print()
    
    def ui_complete_copy(self, parameters, text, current_param):
        if current_param == 'name':
            L = ['@prompt', '@auto']
            for bp in rCache.get_bps():
                L.append(bp['name'])
            completions = [a for a in L
                           if a.startswith(text)]
        elif current_param == 'desc':
            completions = [a for a in ['@prompt', '@auto']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions


class Applications(ConfigNode):
    """Setup the 'applications' node.
    
    Path: /apps/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'apps', parent)
        self.refresh()
    
    def refresh(self):
        rCache.purge_app_cache()
        self._children = set([])
        self.numberOfApps = self.numberOfPublishedApps = 0
        for app in rClient.get_applications():
            if is_admin() and rOpt.showAllApps:
                App(app['name'], self, app['id'])
                if app['published']:
                    self.numberOfPublishedApps += 1
            else:
                if app['name'].startswith(appnamePrefix):
                    App(app['name'].replace(appnamePrefix, ''), self, app['id'])
                    if app['published']:
                        self.numberOfPublishedApps += 1
    
    def summary(self):
        totalActiveVms = get_num_learner_active_vms(user)
        if not self.numberOfApps:
            return ("No applications", False)
        return ("{} active VMs, {} of {} applications published"
                .format(totalActiveVms, self.numberOfPublishedApps, self.numberOfApps), None)
    
    def ui_command_refresh(self):
        """
        Poll Ravello for application list, the same as on initial startup.
        
        There are a few situations where this might come in handy:
            - If you create or delete apps in the Ravello web UI
            - If you create or delete apps in a separate instance of ravshello
            - If you create or delete apps via the API using some other means
        """
        print(c.yellow("\nRefreshing all application data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))
    
    def ui_command_DELETE_ALL(self, noconfirm='false'):
        """
        Delete all user applications.
        
        Allows deleting all apps associated with your username.
        Use noconfirm=true (or simply an arg of true) with care.
        """
        print()
        if is_admin() and rOpt.showAllApps:
            print(c.red("NOPE!\n"
                        "The DELETE_ALL cmd doesn't work when logged in as admin with visibility to all apps\n"))
            print("Log out and use -a/--admin instead of -A/--allapps\n"
                  "That will allow you to quickly delete all apps that include your kerberos in their name\n")
            return
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        if not noconfirm:
            c.slow_print(c.bgRED("  W A R N I N G ! ! ! !"))
            c.slow_print(c.RED("\nPress Ctrl-c now unless you are ABSOLUTELY SURE you want to delete all of your applications!"))
            c.slow_print(c.RED("ARE YOU POSITIVELY CONFIDENT THAT ALL OF YOUR VMs SHOULD BE DESTROYED?"))
            response = raw_input(c.CYAN("\nType 'yes!' in ALL CAPS to continue: "))
            print()
        if noconfirm or response == 'YES!':
            rCache.purge_app_cache()
            for app in rClient.get_applications():
                if app['name'].startswith(appnamePrefix):
                    appName = app['name'].replace(appnamePrefix, '')
                    try:
                        self.get_child(appName).delete_app()
                    except:
                        print(c.yellow("\nThere is a new application available to you since you started {}!".format(cfg.prog)))
                        print("To avoid deleting an app you cannot see, we've refreshed the apps for you ..." +
                              "You'll now need to re-run this command\n")
                        return
            self.refresh()
        else:
            print("Whew! That was close! Leaving your apps alone sounds like a good idea")
        print()
    
    def ui_complete_DELETE_ALL(self, parameters, text, current_param):
        if current_param == 'noconfirm':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_new(self, blueprint='@prompt', name='@prompt',
            desc='@prompt', publish='true', region='@prompt',
            startAllVms='true', allowExactName='false'):
        """
        Interactively create a new application from a base blueprint.
        
        Optionally specify all parameters on the command-line.
        Note that application *name*, *desc*, *region* can be set to '@auto';
        however, due to a limitation in ConfigShell, *desc* cannot accept
        multiple arguments (i.e., you cannot pass multiple words with spaces,
        even if you use quotes).
        
        If run with publish=false, the publish command can be run
        later from the app-specific context (/apps/APPNAME/).
        
        Also note that with the default behavior of allowExactName=false, a
        unique number will be appended to the end of the requested app name in
        order to avoid name collisions.
        """
        blueprint = self.ui_eval_param(blueprint, 'string', '@prompt')
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        publish = self.ui_eval_param(publish, 'bool', True)
        region = self.ui_eval_param(region, 'string', '@prompt')
        startAllVms = self.ui_eval_param(startAllVms, 'bool', True)
        startAllVms = self.ui_type_bool(startAllVms, reverse=True)
        allowExactName = self.ui_eval_param(allowExactName, 'bool', False)
        
        # Check for available blueprints first
        allowedBlueprints = []
        for bp in rCache.get_bps(myOrgOnly=True):
            try:
                description = bp['description']
            except:
                description = ''
            if is_admin() or any(tag in description for tag in cfg.learnerBlueprintTag) or '#k:{}'.format(user) in description:
                allowedBlueprints.append(bp['name'])
        if not allowedBlueprints:
            print(c.red("\nThere are no blueprints available for you to base an application on!\n"))
            return
        
        if blueprint == '@prompt':
            # Print available blueprints
            print(c.BOLD("\nBlueprints available to you:"))
            for i, bp in enumerate(allowedBlueprints):
                print("  {})  {}".format(c.cyan(i), bp))
            
            # Prompt for blueprint selection
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter number of blueprint: "), endRange=i)
            baseBlueprintName = allowedBlueprints[selection]
        else:
            baseBlueprintName = blueprint
            
        # Quit if invalid blueprint name
        if baseBlueprintName not in allowedBlueprints or not ui.iterate_json_keys_for_value(rCache.get_bps(myOrgOnly=True), 'name', baseBlueprintName):
            print(c.RED("\nInvalid blueprint name!\n"))
            return
        
        # Convert blueprint name to id
        for bp in rCache.get_bps(myOrgOnly=True):
            if bp['name'] == baseBlueprintName:
                baseBlueprintId = bp['id']
                break
        
        if name == '@prompt' or name == '@auto':
            # Set default app name based off blueprint name
            appName = c.replace_bad_chars_with_underscores(baseBlueprintName)
            
            if is_admin() and name == '@prompt':
                # Prompt for name if admin
                a = raw_input(c.CYAN("\nEnter a name for your new application [{}]: ".format(appName)))
                if len(a):
                    aFixed = c.replace_bad_chars_with_underscores(a)
                    if a != aFixed:
                        print(c.yellow(
                            "\nNote that configshell (which {} uses) won't accept certain chars in paths\n"
                            "Namely, only the following are allowed: A-Za-z0-9:_.~-\n"
                            "In order handle apps with characters BESIDES those, one would have to use the\n"
                            "*interactive* cd command with arrow keys".format(cfg.prog)))
                        response = raw_input(c.CYAN("\nReplace bad characters with underscores? [y/N] "))
                        if response == 'y':
                            a = aFixed
                    appName = a
        else:
            appName = name
            
        appName = appnamePrefix + appName
        
        # Ensure there's not already an app with that name
        if not allowExactName:
            appName = ravello_sdk.new_name(rClient.get_applications(), appName + '_')
        
        if desc == '@prompt':
            # Prompt for description
            if is_admin():
                appDesc = raw_input(c.CYAN("\nOptionally enter a description for your new app: "))
                if len(appDesc):
                    appDesc += ' '
            else:
                appDesc = ''
        elif desc == '@auto':
            appDesc = ''
        else:
            appDesc = desc
        
        appDesc += "[Created w/{} {} by {}]".format(cfg.prog, cfg.__version__, user)
        
        # Build request dictionary
        req = {'name' : appName, 'description' : appDesc, 'baseBlueprintId': baseBlueprintId}
        
        # Attempt create request!
        try:
            newApp = rClient.create_application(req)
        except:
            print(c.red("\nProblem creating application!\n"))
            raise
        
        # Strip appname prefix for purposes of our UI
        if not rOpt.showAllApps:
            appName = appName.replace(appnamePrefix, '')
        
        print(c.green("\nApplication '{}' created!".format(appName)))
        
        # Add new app to directory tree
        App("%s" % appName, self, newApp['id'])
        
        if publish:
            self.get_child(appName).ui_command_publish(region, startAllVms)
        else:
            print()
    
    def ui_complete_new(self, parameters, text, current_param):
        if current_param == 'blueprint':
            allowedBlueprints = ['@prompt']
            blueprints = rCache.get_bps(myOrgOnly=True)
            for bp in blueprints:
                try:
                    description = bp['description']
                except:
                    description = ''
                if is_admin() or any(tag in description for tag in cfg.learnerBlueprintTag) or '#k:{}'.format(user) in description:
                    allowedBlueprints.append(bp['name'])
            completions = [a for a in allowedBlueprints
                           if a.startswith(text)]
        elif current_param in ['name', 'desc']:
            completions = [a for a in ['@prompt', '@auto']
                           if a.startswith(text)]
        elif current_param in ['publish', 'startAllVms', 'allowExactName']:
            completions = [a for a in ['true', 'false']
                           if a.startswith(text)]
        elif current_param == 'region':
            L = ['@prompt', '@auto']
            try:
                blueprint = parameters['blueprint']
            except:
                completions = [a for a in L
                               if a.startswith(text)]
            else:
                allowedBlueprints = {}
                blueprints = rCache.get_bps(myOrgOnly=True)
                for bp in blueprints:
                    try:
                        description = bp['description']
                    except:
                        description = ''
                    if is_admin() or any(tag in description for tag in cfg.learnerBlueprintTag) or '#k:{}'.format(user) in description:
                        allowedBlueprints[bp['name']] = bp['id']
                try:
                    bpid = allowedBlueprints[blueprint]
                except:
                    completions = [a for a in L
                                   if a.startswith(text)]
                else:
                    pubLocations = [loc for loc in rClient.get_blueprint_publish_locations(bpid)
                                        if not loc['deprecated']]
                    for p in pubLocations:
                        L.append(p['regionDisplayName'].replace(" ", "-"))
                    completions = [a for a in L
                                   if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions


class App(ConfigNode):
    """Setup the dynamically-named app node.
    
    Path: /apps/{APP_NAME}/
    """
    
    def __init__(self, appName, parent, appId):
        ConfigNode.__init__(self, appName, parent)
        parent.numberOfApps += 1
        self.appName = appName
        self.appId = appId
        if not is_admin():
            self.ui_command_save_blueprint = None
        Vms(self)
    
    def summary(self):
        app = rCache.get_app(self.appId)
        owner = app['owner']
        _date = ui.convert_ts_to_date(app['creationTime'], showHours=False)
        try:
            currentDescription = app['description']
            m = re.search('_{(.*)}_', currentDescription)
            if m:
                note = "; {}".format(m.group(1))
            else:
                note = ""
        except:
            note = ""
        if app['published']:
            region = app['deployment']['regionName'].replace(" ", "-")
            totalErrorVms = app['deployment']['totalErrorVms']
            appState = ravello_sdk.application_state(app)
            if isinstance(appState, list):
                if 'STOPPING' in appState:
                    hazHappy = False
                else:
                    hazHappy = True
                appState = ", ".join(appState)
            else:
                if appState == 'STOPPED':
                    hazHappy = None
                elif appState == 'STOPPING':
                    hazHappy = False
                else:
                    hazHappy = True
            if totalErrorVms > 0:
                hazHappy = False
            status = "{owner} created on {date}; {state} in {region}{note}".format(
                owner=owner,
                date=_date,
                state=appState,
                region=region,
                note=note) 
        else:
            status = "{owner} created on {date}; Unpublished draft{note}".format(
                owner=owner,
                date=_date,
                note=note)
            hazHappy = None
        return (status, hazHappy)
    
    def print_message_app_not_published(self):
        print(c.red("\nApplication has not been published yet!\n"))
        print("To publish application, run command:")
        print(c.BOLD("    /apps/{}/ publish\n".format(self.appName)))
    
    def confirm_app_is_published(self, quiet=False):
        published = rClient.is_application_published(self.appId)['value']
        if not (published or quiet):
            self.print_message_app_not_published()
        return published
    
    def ui_command_update_note(self, note='@prompt'):
        """
        Embed an arbitrary string of text in the application description.
        
        Things to keep in mind:
        
        - In Ravello, app descriptions are limited to 255 bytes
        
        - All applications created by ravshello get something like the following
          stored as their initial description:
          
            [Created w/ravshello v1.0.1 by rsawhill]
        
        - When using this command, ravshello keeps the above-mentioned string
          intact if it is already present, meaning that notes created by this
          command could be limited to around ~200 bytes
          
        - When specifying the note non-interactively with note=<SomeNoteHere>,
          you cannot use spaces -- a bummer limitation of ConfigShell!
        """
        print()
        note = self.ui_eval_param(note, 'string', '@prompt')
        if note == '@prompt':
            print(c.BOLD("With this command you can store an arbitrarily free-"
                         "form note about this app"))
            print("(For example, to keep track of learning module progress)\n")
        app = rClient.get_application(self.appId)
        currentDescription = app['description']
        m = re.search(r'(\[.*\]) *_{(.*)}_', currentDescription)
        if note == '@prompt':
            if m:
                print("Current note: '{}'\n".format(m.group(2)))
            else:
                print("No note stored yet\n")
            response = raw_input(c.CYAN("Enter new note\n> "))
            print()
            newNote = " _{" + str(response).strip() + "}_"
        else:
            newNote = " _{" + note.strip() + "}_"
        if m:
            newDescription = m.group(1) + newNote
            allowedNoteLength = 255 - len(m.group(1)) - len(' _{}_')
        else:
            newDescription = currentDescription + newNote
            allowedNoteLength = 255 - len(currentDescription) - len(' _{}_')
        if len(newDescription) > 255:
            print(c.red("Note exceeds allowed length! ({} bytes)\n"
                        .format(allowedNoteLength)))
            return
        app['description'] = newDescription
        print(c.yellow("Saving note to application in the cloud . . . "), end='')
        stdout.flush()
        try:
            rClient.update_application(app)
        except:
            print(c.red("\n\nProblem updating application!\n"))
            raise
        print(c.green("DONE!\n"))
        rCache.purge_app_cache(self.appId)
        if note == '@prompt':
            print("Notes can be seen with the {} command\n"
                  .format(c.BOLD("ls")))
    
    def ui_command_loop_query_status(self, desiredState=None,
            intervalSec=20, totalMin=30):
        """
        Execute query_status command on a loop.
        
        Optionally specify *desiredState* -- loop ends if all VMs reach this
        state (choose between 'STARTED' & 'STOPPED').
        Optionally specify loop interval in seconds via *intervalSec*.
        Optionally specify total loop time in minutes via *totalMin*.
        """
        desiredState = self.ui_eval_param(desiredState, 'string', 'None')
        intervalSec = self.ui_eval_param(intervalSec, 'number', 20)
        totalMin = self.ui_eval_param(totalMin, 'number', 30)
        if not is_admin():
            if intervalSec < 5:
                print(c.red("\nUsing minimum learner interval of 5 sec"))
                intervalSec = 5
            if totalMin > cfg.maxLearnerExtendTime:
                print(c.red("\nUsing maximum learner watch-time of {} min"
                            .format(cfg.maxLearnerExtendTime)))
                totalMin = cfg.maxLearnerExtendTime
            elif totalMin < 1:
                print(c.red("\nUsing minimum learner watch-time of 1 min"))
                totalMin = 1
        self.loop_query_status(desiredState, intervalSec, totalMin)
    
    def ui_complete_loop_query_status(self, parameters, text, current_param):
        if current_param == 'desiredState':
            completions = [a for a in ['STARTED', 'STOPPED']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def loop_query_status(self, desiredState=None, intervalSec=20, totalMin=30):
        maxLoops = totalMin * 60 / intervalSec
        print(c.yellow(
            "\nPolling application every {} secs for next {} mins to display "
            "VM status . . .".format(intervalSec, totalMin)))
        if desiredState:
            print("Will stop polling when all VMs reach '{}' state"
                  .format(desiredState))
        print("(It won't hurt anything if you cancel status loop early with " +
              c.BOLD("Ctrl-c") + ")\n")
        loopCount = 0
        while loopCount <= maxLoops:
            i = intervalSec
            while i >= 0:
                print(c.REVERSE("{}".format(i)), end='')
                stdout.flush()
                sleep(1)
                print('\033[2K', end='')
                i -= 1
            print()
            allVmsStarted, allVmsStopped = self.query_status()
            if desiredState == 'STARTED' and allVmsStarted:
                break
            if desiredState == 'STOPPED' and allVmsStopped:
                break
            loopCount += 1
        
        print(c.green("All VMs reached '{}' state!\n".format(desiredState)))
        if desiredState == 'STARTED':
            c.verbose(
                "SSH NOTE: The VM 'STARTED' state doesn't guarantee an OS has finished booting\n")
            c.verbose(
                "VNC NOTE: URLs expire within a minute if not used; refresh them with command:\n"
                "    \033[0m{}\n".format(c.BOLD("/apps/{} query_status".format(self.appName))))
            c.verbose(
                "CHECK TIMER: The auto-stop timer is counting down; check it with command:\n"
                "    \033[0m{}\n".format(c.BOLD("/apps/{} ls".format(self.appName))))
            c.verbose(
                "EXTEND TIMER: If you need more time, make sure to use the command:\n"
                "    \033[0m{}\n".format(c.BOLD("/apps/{} extend_autostop".format(self.appName))))
    
    def ui_command_query_status(self):
        """
        Query an app to get full details about all its VMs.
        
        Once the app has reached STARTED state, the following details might be
        available for display:
            - internal DNS names
            - internal IP addrs
            - externally-available ports
            - external FQDNs (generally used for ssh)
            - VNC web URLs
        """
        print()
        self.query_status()
    
    def query_status(self):
        app = rClient.get_application(self.appId, aspect='deployment')
        if not app['published']:
            self.print_message_app_not_published()
            return None, None
        # Defaults
        allVmsAreStarted = True
        allVmsAreStopped = True
        try:
            expirationTime = ui.sanitize_timestamp(app['deployment']['expirationTime'])
        except:
            expirationTime = None
        if expirationTime:
            diff = expirationTime - time()
            m, s = divmod(expirationTime - time(), 60)
            expireDateTime = datetime.fromtimestamp(expirationTime)
            if diff < 0:
                autoStopMessage = c.BOLD("were auto-stopped on {}".format(
                    expireDateTime.strftime('%Y/%m/%d @ %H:%M')))
            else:
                t = "{:.0f}:{:02.0f}".format(m, s)
                if m <= 4:
                    timestring = c.bgRED(t)
                elif m <= 15:
                    timestring = c.RED(t)
                elif m <= 30:
                    timestring = c.YELLOW(t)
                else:
                    timestring = c.GREEN(t)
                autoStopMessage = c.BOLD("will auto-stop in {}".format(timestring))
                autoStopMessage += c.BOLD(" min at {}".format(expireDateTime.strftime('%H:%M:%S')))
        else:
            autoStopMessage = c.BOLD("never had auto-stop set")
        # Print our header message
        region = app['deployment']['regionName'].replace(" ", "-")
        print(c.BOLD("App VMs in region {} {}".format(region, autoStopMessage)))
        print()
        for vm in app['deployment']['vms']:
            # Set variables for return
            if vm['state'] not in 'STARTED':
                allVmsAreStarted = False
            if vm['state'] not in 'STOPPED':
                allVmsAreStopped = False
            out = get_vm_access_details(vm)[0]
            print("  ", end="")
            print("\n  ".join(out))
            print()
        return allVmsAreStarted, allVmsAreStopped
    
    def extend_autostop(self, minutes=60):
        req = {'expirationFromNowSeconds': minutes * 60}
        try:
            rClient.set_application_expiration(self.appId, req)
        except:
            print(c.red("\nProblem setting application auto-stop!"))
            raise
        print(c.green("\nApp auto-stop set for {} minutes from now"
                      .format(minutes)))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_extend_autostop(self, minutes=cfg.defaultAppExtendTime):
        """
        Set the application auto-stop time via *minutes*.
        
        Defaults to 60 min (defaultAppExtendTime). Learners can set the
        auto-stop timer from 0 to 120 min (maxLearnerExtendTime).
        Admins can set any value, including '-1' which disables auto-stop timer.
        """
        minutes = self.ui_eval_param(minutes, 'number', cfg.defaultAppExtendTime)
        if not self.confirm_app_is_published():
            return
        if not is_admin():
            if minutes > cfg.maxLearnerExtendTime:
                print(c.red("\nUsing maximum learner auto-stop time of {} minutes"
                            .format(cfg.maxLearnerExtendTime)))
                minutes = cfg.maxLearnerExtendTime
            elif minutes < 0:
                print(c.RED("\nInvalid learner auto-stop time\n"))
                return
        self.extend_autostop(minutes)
        print()
    
    def ui_complete_extend_autostop(self, parameters, text, current_param):
        if current_param == 'minutes':
            if is_admin():
                L = ['-1', '5', '30', '60', '120', '240', '480', '720', '1440']
            else:
                L = ['5', '15', '30', '45', '60', '90', '120']
            completions = [a for a in L
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_print_def(self, outputFile='@EDITOR', aspect='@auto'):
        """
        Pretty-print app JSON in pager or export to *outputFile*.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        
        Optionally specify *aspect* as 'deployment' or 'design' or
        'properties'. Default value of '@auto' chooses deployment if published
        and design if unpublished.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        aspect = self.ui_eval_param(aspect, 'string', '@auto')
        if aspect == 'deployment' and not self.confirm_app_is_published():
            return
        if aspect == '@auto':
            if self.confirm_app_is_published(quiet=True):
                aspect = 'deployment'
            else:
                aspect = 'design'
        description = "APP {} definition for /apps/{}".format(aspect, self.appName)
        obj = rClient.get_application(self.appId, aspect=aspect)
        ui.print_obj(obj, description, outputFile, tmpPrefix=self.appName)
    
    def ui_command_save_blueprint(self, name='@prompt', desc='@prompt', shutdown='true',
            waitSnapshotCompletion='true', allowExactName='false'):
        """
        Interactively create a new blueprint from application.
        
        Optionally specify all parameters on the command-line.
        Note that blueprint *name* & *desc* can be set to '@auto' -- this bases
        them off of the application name and description.
        
        Note: due to a limitation in ConfigShell, *desc* cannot accept
        multiple arguments (i.e., you cannot pass multiple words with spaces,
        even if you use quotes).

        *shutdown* defaults to 'true', in which case it will ensure the app
        is stopped prior to taking the snapshot. This is of course
        recommended -- taking snapshots of running machines is not a good
        idea.
        
        *waitSnapshotCompletion* defaults to 'true', in which case the command
        will not return until each VM's 'loadingStatus' attribute has returned
        to the 'DONE' state. The VM will not respond to start commands until
        this  is the case (at least for offline [shutdown=true] snapshots).
        
        Also note that with the default behavior of allowExactName=false, a
        unique number will be appended to the end of the requested BP name in
        order to avoid name collisions.
        """
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        waitSnapshotCompletion = self.ui_eval_param(waitSnapshotCompletion, 'bool', True)
        shutdown = self.ui_eval_param(shutdown, 'bool', True)
        allowExactName = self.ui_eval_param(allowExactName, 'bool', False)
        bpName = c.replace_bad_chars_with_underscores(rCache.get_app(self.appId)['name'])
        if name == '@prompt':
            a = raw_input(c.CYAN("\nEnter a name for the new blueprint [{}]: ".format(bpName)))
            if len(a):
                aFixed = c.replace_bad_chars_with_underscores(a)
                if a != aFixed:
                    print(c.yellow(
                        "\nNote that configshell (which {} uses) won't accept certain chars in paths\n"
                        "Namely, only the following are allowed: A-Za-z0-9:_.~-\n"
                        "In order handle apps with characters BESIDES those, one would have to use the\n"
                        "*interactive* cd command with arrow keys".format(cfg.prog)))
                    response = raw_input(c.CYAN("\nReplace bad characters with underscores? [y/N] "))
                    if response == 'y':
                        a = aFixed
                bpName = a
            name = bpName
        elif name == '@auto':
            name = bpName
        # Ensure there's not already a bp with that name
        if not allowExactName:
            name = ravello_sdk.new_name(rCache.get_bps(myOrgOnly=True), name + '_')
        if desc == '@prompt':
            desc = raw_input(c.CYAN("\nOptionally enter a description for your new app: "))
            if len(desc):
                desc += ' '
            else:
                desc = ''
        elif desc == '@auto':
            desc = ''
        else:
            desc += ' '
        desc += "[Created w/{} {} by {} from app '{}']".format(cfg.prog, cfg.__version__, user, self.appName)
        req = {'applicationId': self.appId, 'blueprintName': name, 'offline': shutdown, 'description': desc}
        print(c.yellow("\nSaving blueprint from application . . . "), end="")
        stdout.flush()
        # Attempt create request!
        try:
            newBp = rClient.create_blueprint(req)
        except:
            print(c.red("\n\nProblem creating blueprint!\n"))
            raise
        print(c.green("DONE!\n\nCreated new blueprint: {}\n".format(newBp['name'])))
        rCache.purge_bp_cache()
        if not waitSnapshotCompletion:
            return
        print(c.yellow("Waiting for all VMs to finish snapshotting . . ."))
        while 1:
            app = rClient.get_application(self.appId, aspect='deployment')
            status = list(set([vm['loadingStatus'] for vm in app['deployment']['vms']]))
            if len(status) == 1 and 'DONE' in status:
                break
            i = 30
            while i >= 0:
                print(c.REVERSE("{}".format(i)), end='', file=stderr)
                stderr.flush()
                sleep(1)
                print('\033[2K', end='', file=stderr)
                i -= 1
            print(file=stderr)
        print(c.green("DONE!\n"))

    
    def ui_complete_save_blueprint(self, parameters, text, current_param):
        if current_param in ['name', 'desc']:
            completions = [a for a in ['@prompt', '@auto']
                           if a.startswith(text)]
        elif current_param in ['shutdown', 'waitSnapshotCompletion', 'allowExactName']:
            completions = [a for a in ['true', 'false']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param == 'aspect':
            L = ['@auto', 'deployment', 'design', 'properties']
            completions = [a for a in L
                           if a.startswith(text)]
            if len(completions) == 1:
                completions = [completions[0] + ' ']
        else:
            completions = []
        return completions
    
    def ui_command_find_pub_locations(self, outputFile='@EDITOR'):
        """
        Print details about available publish locations for an app.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "APP available publish locations for /apps/{}".format(self.appName)
        ui.print_obj(rClient.get_application_publish_locations(self.appId),
            description, outputFile, tmpPrefix='publoc_{}'.format(self.appName))
    
    def delete_app(self):
        if self.confirm_app_is_published(quiet=True):
            published = True
        else:
            published = False
        try:
            rClient.delete_application(self.appId)
        except:
            print(c.red("Problem deleting app!\n"))
            raise
        if published:
            self.parent.numberOfPublishedApps -= 1
        rCache.purge_app_cache(self.appId)
        self.parent.numberOfApps -= 1
        print(c.green("Deleted application {}".format(self.appName)))
        self.parent.remove_child(self)
    
    def ui_command_delete(self, noconfirm='false'):
        """
        Delete an application.
        
        By default, confirmation will be required to delete the application.
        Disable prompt with noconfirm=true (or simply argument of true).
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        print()
        if not noconfirm:
            c.slow_print(c.RED("Deleting an application cannot be undone -- All VM data will be lost\n"))
            response = raw_input(c.CYAN("Continue? [y/N] "))
            print()
        if noconfirm or response == 'y':
            self.delete_app()
        else:
            print("Leaving app intact (probably a good choice)")
        print()
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param == 'noconfirm':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def publish_design_updates(self):
        try:
            rClient.publish_application_updates(self.appId)
        except:
            print(c.red("\nProblem publishing application design updates to cloud!\n"))
            raise
        print(c.green("\nPublished application design updates to cloud\n"))

    def ui_command_publish_design_updates(self):
        """
        Update the cloud with the latest design updates.
        """
        if self.confirm_app_is_published():
            self.publish_design_updates()
    
    def ui_command_publish(self, region='@prompt', startAllVms='true', loopQueryStatus='true'):
        """
        Interactively publish an application to the cloud.
        
        Optionally specify *region* and whether all VMs should be started after
        publishing (*startAllVms*).
        """
        region = self.ui_eval_param(region, 'string', '@prompt')
        startAllVms = self.ui_eval_param(startAllVms, 'bool', True)
        loopQueryStatus = self.ui_eval_param(loopQueryStatus, 'bool', True)
        # Sanity check
        if self.confirm_app_is_published(quiet=True):
            print(c.red("\nApplication already published!\n"))
            return
        # Set defaults
        selection = preferredRegion = None
        if not is_admin():
            # Check that we don't have more published apps than we should
            totalActiveVms = get_num_learner_active_vms(user)
            if self.parent.numberOfPublishedApps >= cfg.maxLearnerPublishedApps:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of published apps!"
                            .format(cfg.maxLearnerPublishedApps)))
                print("Delete an app and try running command:")
                print(c.BOLD("    /apps/{}/ publish\n".format(self.appName)))
                return
            elif totalActiveVms >= cfg.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!"
                            .format(cfg.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try running command:")
                print(c.BOLD("    /apps/{}/ start\n".format(self.appName)))
                return
        # Choosing time
        pubLocations = [loc for loc in rClient.get_application_publish_locations(self.appId)
                            if not loc['deprecated']]
        # Replace spaces in displayName with dashes
        for loc in pubLocations:
            loc['regionDisplayName'] = loc['regionDisplayName'].replace(" ", "-")
        # Somewhat ironically, we only add cost-optimized option for admins
        if is_admin():
            pubLocations.insert(0, {'regionName': "@auto", 'regionDisplayName': "@auto"})
        if region == '@prompt':
            print(c.BOLD("\nAvailable publish locations:"))
            for i, loc in enumerate(pubLocations):
                print("  {})  {}".format(c.cyan(i), loc['regionDisplayName']))
            # Prompt for provider selection
            selection = ui.prompt_for_number(
                c.CYAN("\nSelect cloud region in which to provision your VMs by entering a number: "),
                endRange=i)
            if '@auto' in pubLocations[selection]['regionDisplayName']:
                optimizationLevel = 'COST_OPTIMIZED'
            else:
                optimizationLevel = 'PERFORMANCE_OPTIMIZED'
                preferredRegion = pubLocations[selection]['regionName']
        elif region == '@auto':
            optimizationLevel = 'COST_OPTIMIZED'
        else:
            for i, loc in enumerate(pubLocations):
                if region in [loc['regionName'], loc['regionDisplayName']]:
                    optimizationLevel = 'PERFORMANCE_OPTIMIZED'
                    preferredRegion = loc['regionName']
                    break
            else:
                print(c.RED("Invalid region specified!\n"))
                return
        # Build request dictionary
        req = {'preferredRegion' : preferredRegion,
               'optimizationLevel': optimizationLevel, 'startAllVms': startAllVms}
        # Attempt publish request
        try:
            rClient.publish_application(self.appId, req)
        except:
            print(c.red("\nProblem creating application!\n"))
            raise
        self.parent.numberOfPublishedApps += 1
        print(c.yellow("\nRavello now publishing your application (Could take a while)"))
        # Configure auto-stop
        if startAllVms:
            self.extend_autostop(minutes=cfg.defaultAppExpireTime)
            if loopQueryStatus:
                self.loop_query_status(desiredState='STARTED')
        else:
            rCache.purge_app_cache(self.appId)
            print()
    
    def ui_complete_publish(self, parameters, text, current_param):
        if current_param == 'region':
            L = ['@prompt', '@auto']
            pubLocations = [loc for loc in rClient.get_application_publish_locations(self.appId)
                                if not loc['deprecated']]
            for p in pubLocations:
                L.append(p['regionDisplayName'].replace(" ", "-"))
            completions = [a for a in L
                           if a.startswith(text)]
        elif current_param in ['startAllVms', 'loopQueryStatus']:
            completions = [a for a in ['true', 'false']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_start(self, loopQueryStatus='true'):
        """
        Start a stopped application.
        
        Attempts to start all VMs in the application.
        """
        loopQueryStatus = self.ui_eval_param(loopQueryStatus, 'bool', True)
        if not self.confirm_app_is_published():
            return
        if not is_admin():
            # Check that we don't have more started VMs than we should
            totalActiveVms = get_num_learner_active_vms(user)
            if totalActiveVms >= cfg.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!\n"
                            .format(cfg.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try this again")
                return
        # Start out by setting autostop
        self.extend_autostop(minutes=cfg.defaultAppExpireTime)
        try:
            rClient.start_application(self.appId)
        except:
            print(c.red("\nProblem starting application!\n"))
            raise
        print(c.yellow("\nApplication now starting"))
        rCache.purge_app_cache(self.appId)
        if loopQueryStatus:
            self.loop_query_status(desiredState='STARTED')
        else:
            print()
    
    def ui_complete_start(self, parameters, text, current_param):
        if current_param in ['loopQueryStatus']:
            completions = [a for a in ['true', 'false']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_Stop(self):
        """
        Stop a running application.
        
        Sends a shutdown (via ACPI) to all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        try:
            rClient.stop_application(self.appId)
        except:
            print("\nProblem stopping application!\n")
        print(c.yellow("\nApplication now stopping\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_restart(self):
        """
        Restart a running application.
        
        Sends a reboot (via ACPI) to all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        self.extend_autostop(minutes=cfg.defaultAppExpireTime)
        try:
            rClient.restart_application(self.appId)
        except:
            print("\nProblem restarting application!\n")
            raise
        print(c.yellow("\nApplication now restarting"))
        rCache.purge_app_cache(self.appId)
        self.loop_query_status(desiredState='STARTED')
    
    def generate_images(self):
        """Generate snapshot of all vms in the app. Not ready for primetime."""
        appDetails = rCache.get_app(self.appId)
        for i in range(len(appDetails['design']['vms'])):
            print("\n Generating snapshot for vm ",appDetails['design']['vms'][i]['name'])
            imageName = c.replace_bad_chars_with_underscores(appDetails['name'])
            imageName = appnamePrefix + imageName
            a = raw_input("\nEnter a name for your vm image [{}]: ".format(imageName))
            if a:
                imageName = c.replace_bad_chars_with_underscores(a)
            applicationId = appDetails['design']['vms'][i]['applicationId']
            vmId = appDetails['design']['vms'][i]['id']
            imageReq = {"applicationId": applicationId, "blueprint": "false", "vmId": vmId, "offline": "true", "imageName": imageName}
            try:
                newImg = rClient.create_images(imageReq)
            except:
                raise
            print("\n New image {} is created for vm {}".format(newImg['name'],appDetails['design']['vms'][i]['name']))
        print()



class Vms(ConfigNode):
    """Setup the dynamically-named vm node.
    
    Path: /apps/{APP_NAME}/vms/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'vms', parent)
        self.appId = parent.appId
        self.appName = parent.appName
        for vm in rClient.get_vms(self.appId):
            Vm("%s" % vm['name'], self, vm['id'])
    
    def summary(self):
        app = rCache.get_app(self.appId)
        if app['published']:
            totalVms = len(app['deployment']['vms'])
            totalActiveVms = app['deployment']['totalActiveVms']
            totalErrorVms = app['deployment']['totalErrorVms']
            try:
                expirationTime = ui.sanitize_timestamp(app['deployment']['expirationTime'])
            except:
                expirationTime = None
            status = "{}/{} active".format(totalActiveVms, totalVms)
            if totalActiveVms > 0:
                hazHappy = True
                if expirationTime:
                    diff = expirationTime - time()
                    m, s = divmod(expirationTime - time(), 60)
                    expireDateTime = datetime.fromtimestamp(expirationTime)
                    if diff < 0:
                        status += ", auto-stopped on {}".format(
                            expireDateTime.strftime('%Y/%m/%d @ %H:%M'))
                    elif m > 0:
                        status += ", auto-stop in {:.0f}:{:02.0f} min".format(m, s)
                    else:
                        status += ", auto-stop in {:02.0f} sec".format(s)
                else:
                    status += ", auto-stop disabled"
            else:
                hazHappy = None
            if totalErrorVms > 0:
                status += "({} VMs in error state!)".format(totalErrorVms)
                hazHappy = False
            return (status, hazHappy)
        else:
            return ("", None)


class Vm(ConfigNode):
    """Setup the 'vms' node.
    
    Path: /apps/{APP_NAME}/vms/{VM_NAME}/
    """
    
    def __init__(self, name, parent, vmId):
        ConfigNode.__init__(self, name, parent)
        self.appId = parent.appId
        self.appName = parent.appName
        self.vmId = vmId
        self.vmName = name
        self.validNicDeviceTypes = [
            'e1000',
            'virtio',
            'vmxnet3',
            'pcnet',
            'rtl8139',
            'ne2k_pci',
            'vmxnet',
            'e1000e',
            ]
    
    def summary(self):
        app = rCache.get_app(self.appId)
        if app['published']:
            happyStates = ['STARTED', 'STARTING', 'RESTARTING', 'PUBLISHING' ]
            for vm in app['deployment']['vms']:
                if int(vm['id']) == self.vmId:
                    if vm['state'] in happyStates:
                        hazHappy = True
                    elif vm['state'] == 'STOPPED':
                        hazHappy = None
                    else:
                        hazHappy = False
                    return (vm['state'], hazHappy)
        else:
            return (None, None)
    
    def confirm_vm_is_state(self, state):
        for vm in rClient.get_application(self.appId)['deployment']['vms']:
            if vm['id'] == self.vmId:
                if vm['state'] in state:
                    return True
                else:
                    print(c.red("\nVM is not {}!\n".format(state.lower())))
                    return False
        else:
            return False
    
    def confirm_app_is_published(self, quiet=False):
        return self.parent.parent.confirm_app_is_published(quiet)
    
    def ui_command_print_def(self, outputFile='@EDITOR', aspect='@auto'):
        """
        Pretty-print JSON defininition of VM.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then finally less.
        
        Optionally specify *aspect* as 'deployment' or 'design'. Default value
        of '@auto' chooses deployment if published and design if unpublished.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        aspect = self.ui_eval_param(aspect, 'string', '@auto')
        if aspect == 'deployment' and not self.confirm_app_is_published():
            return
        if aspect == '@auto':
            if self.confirm_app_is_published(quiet=True):
                aspect = 'deployment'
            else:
                aspect = 'design'
        description = "VM {} definition for /apps/{}/vms/{}".format(aspect, self.appName, self.vmName)
        obj = rClient.get_vm(self.appId, self.vmId, aspect=aspect)
        ui.print_obj(obj, description, outputFile,
            tmpPrefix='vm_{}_{}'.format(self.appName, self.vmName))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param == 'aspect':
            L = ['@auto', 'deployment', 'design']
            completions = [a for a in L
                           if a.startswith(text)]
            if len(completions) == 1:
                completions = [completions[0] + ' ']
        else:
            completions = []
        return completions
    
    def ui_command_ssh_cmd(self, outputFile='@term', quiet='false',
            loopUntilSuccess='false', intervalSec=20, totalMin=30):
        """
        Get ssh command that could be used to ssh into deployed VM.
        
        When *outputFile* is set to anything other than default of '@term',
        the name=value pairs will be written to that file, e.g.:
            ssh_port='22'
            ssh_fqdn='myvm-myapp-izmow52k.srv.ravcloud.com'
            ssh_key='~/some/ssh/pubkey'
        
        With *quiet* set to default of 'false', extra details are printed to
        the screen, regardless of the value of *outputFile*.
        
        With quiet=true and outputFile=@term, only the ssh command is printed
        (with no extra explanation, colors, etc). With quiet=true and
        outputFile=FILE, only the name=value pairs are saved to FILE. In all
        cases, some warnings/notifications might be printed to stderr.
        
        With *loopUntilSuccess* set 'true', ravshello will keep looping until
        the VM provides ssh details or until the VM reaches STARTED state. You
        can optionally modify loop interval in seconds via *intervalSec* or
        total loop time in minutes via *totalMin*. If *outputFile* is specified
        in this mode, it will be initially truncated but then data will only be
        written on the final (successful) iteration of the loop.
        """
        outputFile = self.ui_eval_param(outputFile, 'string', '@term')
        quiet = self.ui_eval_param(quiet, 'bool', False)
        loopUntilSuccess = self.ui_eval_param(loopUntilSuccess, 'bool', False)
        intervalSec = self.ui_eval_param(intervalSec, 'number', 20)
        totalMin = self.ui_eval_param(totalMin, 'number', 30)
        maxLoops = totalMin * 60 / intervalSec
        print()
        if not self.confirm_app_is_published():
            return
        if outputFile == '@term':
            outputFile = None
        else:
            try:
                f = open(path.expanduser(outputFile), 'w')
            except:
                print(c.red("Error opening outputFile for writing!\n"), file=stderr)
                raise
        if loopUntilSuccess:
            if not is_admin():
                if intervalSec < 5:
                    if not quiet:
                        print(c.yellow("Using minimum learner interval of 5 sec"), file=stderr)
                    intervalSec = 5
                if totalMin > cfg.maxLearnerExtendTime:
                    if not quiet:
                        print(c.yellow("Using maximum learner watch-time of {} min"
                            .format(cfg.maxLearnerExtendTime)), file=stderr)
                    totalMin = cfg.maxLearnerExtendTime
                elif totalMin < 1:
                    if not quiet:
                        print(c.yellow("Using minimum learner watch-time of 1 min"), file=stderr)
                    totalMin = 1
            print(c.yellow("Polling application every {} secs for next {} mins or until VM has STARTED or provided ssh details . . .\n"
                .format(intervalSec, totalMin)), file=stderr)
        loopCount = 0
        while loopCount <= maxLoops:
            vm = rClient.get_vm(self.appId, self.vmId, aspect='deployment')
            ssh_fqdn = ssh_port = ssh_key = None
            if not ('networkConnections' in vm or 'suppliedServices' in vm):
                pass
            else:
                ssh_key = cfg.cfgFile.get('sshKeyFile', '')
                for nic in vm['networkConnections']:
                    fqdn = nic['ipConfig'].get('fqdn', '')
                    if not fqdn:
                        continue
                    for svc in vm.get('suppliedServices', []):
                        if svc['name'] == 'ssh' and svc['external'] and 'externalPort' in svc and svc['useLuidForIpConfig'] and nic['ipConfig']['id'] == svc['ipConfigLuid']:
                            ssh_fqdn = fqdn
                            ssh_port = svc['externalPort']
                            break
            if ssh_fqdn:
                sshKey = ""
                port = ""
                if ssh_key:
                    sshKey = " -i {}".format(ssh_key)
                if ssh_port != "22":
                    port = " -p {}".format(ssh_port)
                sshCommand = "ssh{}{} root@{}".format(sshKey, port, ssh_fqdn)
                if quiet:
                    if outputFile:
                        pass
                    else:
                        print(sshCommand)
                else:
                    print(c.BOLD(self.vmName))
                    print("   SSH Command:  {}".format(c.cyan(sshCommand)))
                if outputFile:
                    print("ssh_fqdn='{}'".format(ssh_fqdn), file=f)
                    print("ssh_port='{}'".format(ssh_port), file=f)
                    print("ssh_key='{}'".format(ssh_key), file=f)
                    f.close()
                    print(c.green("\nExported SSH details returned by VM {} to file: '{}'"
                        .format(self.vmName, outputFile)), file=stderr)
                break
            else:
                if vm['state'] == 'STARTED':
                    print(c.red("None of the suppliedServices of VM {} are named 'ssh'"
                        .format(self.vmName)), file=stderr)
                elif loopUntilSuccess and quiet:
                    pass
                else:
                    print(c.yellow("None of the suppliedServices of VM {} are named 'ssh' yet (VM not yet STARTED)"
                        .format(self.vmName)), file=stderr)
                if vm['state'] == 'STARTED' or not loopUntilSuccess:
                    break
            i = intervalSec
            loopCount += 1
            while i >= 0:
                print(c.REVERSE("{}".format(i)), end='', file=stderr)
                stderr.flush()
                sleep(1)
                print('\033[2K', end='', file=stderr)
                i -= 1
            print(file=stderr)
        print()
    
    def ui_complete_ssh_cmd(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param in ['loopUntilSuccess', 'quiet']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_query_status(self, outputFile='@term', quiet='false',
            loopUntilStarted='false', intervalSec=20, totalMin=30):
        """
        Query a VM to get full details about it.
        
        When *outputFile* is set to anything other than default of '@term',
        or if *quiet* is set 'true', name=value pairs will be written, e.g.:
            vm_name='myvm'
            vm_state='STARTED'
            internal_hostnames='rhel7.example.com,othername.dom.example.com'
            interfaces='eth0,eth1'
            eth0_internal_ip='10.0.0.1'
            eth0_extra_internal_ips='192.168.1.1,10.1.1.1'
            eth0_public_ip=''
            eth0_public_ip_type=''
            eth0_public_fqdn=''
            eth1_internal_ip='10.200.200.50'
            eth1_extra_internal_ips=''
            eth1_public_ip='104.1.1.1.'
            eth1_public_ip_type='forwarding'
            eth1_public_fqdn='myvm-myapp-izmow52k.srv.ravcloud.com'
            eth1_service_0_name='ssh'
            eth1_service_0_proto='TCP'
            eth1_service_0_externalport='10001'
            eth1_service_0_inport_range='22'
            eth1_service_1_name='http'
            eth1_service_1_proto='TCP'
            eth1_service_1_externalport='10002'
            eth1_service_1_inport_range='80'
            eth1_service_2_name='https'
            eth1_service_2_proto='TCP'
            eth1_service_2_externalport='10003'
            eth1_service_2_inport_range='443'
            ssh_fqdn='myvm-myapp-izmow52k.srv.ravcloud.com'
            ssh_port='10001'
            ssh_key=''
            vnc='https://vnc-us-east-1.ravellosystems.com/vnc/?token=Dc41NcLsCS...'
            timestamp='1489475068'

        With *quiet* set to default of 'false', the above content is printed in a
        pretty/organized way to stdout (just like /apps/APP query_status),
        regardless of the value of *outputFile*.
        
        With quiet=true and outputFile=@term, only the above content (ready for
        scripted-consumption) is printed to stdout. With quiet=true and
        outputFile=FILE, only the name=value pairs are saved to FILE.
        
        With *loopUntilStarted* set 'true', you can optionally modify loop
        interval in seconds via *intervalSec* or total loop time in minutes
        via *totalMin*. If *outputFile* is specified in this mode, it will
        be updated on each iteration of the loop, but the loop will not finish
        until the VM has started.
        """
        outputFile = self.ui_eval_param(outputFile, 'string', '@term')
        quiet = self.ui_eval_param(quiet, 'bool', False)
        loopUntilStarted = self.ui_eval_param(loopUntilStarted, 'bool', False)
        intervalSec = self.ui_eval_param(intervalSec, 'number', 20)
        totalMin = self.ui_eval_param(totalMin, 'number', 30)
        maxLoops = totalMin * 60 / intervalSec
        print()
        if not self.confirm_app_is_published():
            return
        if outputFile == '@term':
            outputFile = None
        if loopUntilStarted:
            if not is_admin():
                if intervalSec < 5:
                    if not quiet:
                        print(c.yellow("Using minimum learner interval of 5 sec"), file=stderr)
                    intervalSec = 5
                if totalMin > cfg.maxLearnerExtendTime:
                    if not quiet:
                        print(c.yellow("Using maximum learner watch-time of {} min"
                            .format(cfg.maxLearnerExtendTime)), file=stderr)
                    totalMin = cfg.maxLearnerExtendTime
                elif totalMin < 1:
                    if not quiet:
                        print(c.yellow("Using minimum learner watch-time of 1 min"), file=stderr)
                    totalMin = 1
            print(c.yellow("Polling application every {} secs for next {} mins or until VM has STARTED . . .\n"
                .format(intervalSec, totalMin)), file=stderr)
        loopCount = 0
        while loopCount <= maxLoops:
            vm = rClient.get_vm(self.appId, self.vmId, aspect='deployment')
            out, deets = get_vm_access_details(vm)
            if not quiet:
                print("\n".join(out))
            if quiet or outputFile:
                if outputFile:
                    try:
                        f = open(path.expanduser(outputFile), 'w')
                    except:
                        print(c.red("Error opening outputFile for writing!\n"), file=stderr)
                        raise
                else:
                    f = stdout
                print("rav_vm_name='{}'".format(vm['name']), file=f)
                print("rav_vm_state='{}'".format(vm['state']), file=f)
                print("rav_internal_hostnames='{}'".format(",".join(vm.get('hostnames', []))), file=f)
                print("rav_interfaces='{}'".format(",".join([n['name'] for n in deets['nics']])), file=f)
                for n in deets['nics']:
                    eth = n['name']
                    print("rav_{}_internal_ip='{}'".format(eth, n['internalIP']), file=f)
                    print("rav_{}_extra_internal_ips='{}'".format(eth, ",".join(n['internalIPs'])), file=f)
                    print("rav_{}_public_ip='{}'".format(eth, n['publicIP']), file=f)
                    print("rav_{}_public_ip_type='{}'".format(eth, n['publicIPtype']), file=f)
                    print("rav_{}_public_fqdn='{}'".format(eth, n['fqdn']), file=f)
                    for j, s in enumerate(n['services']):
                        print("rav_{eth}_service_{j}_name='{name}'".format(eth=eth, j=j, name=s['name']), file=f)
                        print("rav_{eth}_service_{j}_proto='{proto}'".format(eth=eth, j=j, proto=s['protocol']), file=f)
                        print("rav_{eth}_service_{j}_externalport='{port}'".format(eth=eth, j=j, port=s['externalPort']), file=f)
                        print("rav_{eth}_service_{j}_inport_range='{port}'".format(eth=eth, j=j, port=s['portRange']), file=f)
                for k in ['ssh_fqdn', 'ssh_port', 'ssh_key', 'vnc']:
                    print("rav_{}='{}'".format(k, deets[k]), file=f)
                print("rav_timestamp='{:.0f}'".format(time()), file=f)
                if outputFile:
                    f.close()
                    if vm['state'] == 'STARTED':
                        print(c.green("\nExported access details returned by started VM {} to file: '{}'".format(self.vmName, outputFile)), file=stderr)
                        break
            if vm['state'] == 'STARTED' or not loopUntilStarted:
                break
            i = intervalSec
            loopCount += 1
            while i >= 0:
                print(c.REVERSE("{}".format(i)), end='', file=stderr)
                stderr.flush()
                sleep(1)
                print('\033[2K', end='', file=stderr)
                i -= 1
            print(file=stderr)
        print()
    
    def ui_complete_query_status(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        elif current_param in ['loopUntilStarted', 'quiet']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_start(self):
        """
        Start a stopped VM.
        
        The start, Stop, & restart commands all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STOPPED'):
            return
        self.parent.parent.extend_autostop(minutes=cfg.defaultAppExtendTime)
        try:
            rClient.start_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem starting VM!\n"))
            raise
        print(c.yellow("\nVM now starting\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_reset_to_last_shutdown_state(self):
        """
        Reset VM to the state it was in as of last shutdown.
        
        Every VM has its disk state automatically snapshotted at shutdown.
        This command re-publishes the VM using the last snapshot state (which is
        not necessarily the best working state).
        
        To reset a VM to a pristine state (i.e., the state of the VM when the
        app was originally created), you must first ensure the VM never shuts
        down ... or make sure you run this command before any shutdown.
        """
        if not self.confirm_app_is_published():
            return
        try:
            rClient.redeploy_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem resetting VM!\n"))
            raise
        print(c.yellow("\nVM was destroyed and is being re-published from state of last full shutdown"))
        print("FQDN should stay the same; VNC URL will change; ssh host key might change\n")
        rCache.purge_app_cache(self.appId)
    
    def ui_command_Stop(self):
        """
        Gracefully stop a running VM.
        
        The start, Stop, & restart commands all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STARTED'):
            return
        try:
            rClient.stop_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem stopping VM!\n"))
            raise
        print(c.yellow("\nVM now stopping\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_poweroff(self):
        """
        Cut the power to a VM, hopefully forcing it off immediately.
        
        Sadly, this does not always work.
        In particularl, Ravello has a bug where VMs in 'STOPPING' state don't
        respond to this.
        """
        if not self.confirm_app_is_published():
            return
        #~ if not self.confirm_vm_is_state('STARTED'):
            #~ return
        try:
            rClient.poweroff_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem powering off VM!\n"))
            raise
        print(c.yellow("\nVM should be immediately forced off\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_restart(self):
        """
        Gracefully restart a running VM.
        
        The start, Stop, & restart commands all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STARTED'):
            return
        try:
            rClient.restart_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem restarting VM!\n"))
            raise
        print(c.yellow("\nVM now restarting\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_repair(self):
        """
        Repair a VM that has entered an ERROR state.
        
        ERROR states are usually caused by problems on the hypervisor (e.g., a
        Ravello/Amazon/Google problem). They can't always be fixed by using a
        repair call.
        """
        if not self.confirm_app_is_published():
            return
        try:
            rClient.repair_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem repairing VM!\n"))
            raise
        print(c.yellow("\nAPI 'repair' call was sent; check VM status\n"))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_cloudinit_enable(self, enabled='true', publishUpdates='true'):
        """
        Enable or (disable) Cloud-Init for this VM.
        """
        enabled = self.ui_eval_param(enabled, 'bool', True)
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        if self.confirm_app_is_published(quiet=True):
            # FIXME: We should be checking if the **VM** is published; not the app
            print(c.red("Cloud Init cannot be modified after VM is published!\n"))
            return
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if enabled:
            adjective = "enabled"
        else:
            adjective = "disabled"
        if vm['supportsCloudInit'] == enabled:
            print(c.yellow("No change was made! Cloud-Init is already {} for this VM!\n".format(adjective)))
            return
        vm['supportsCloudInit'] = enabled
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_cloudinit_enable(self, parameters, text, current_param):
        if current_param in ['enabled', 'publishUpdates']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_cloudinit_keypair(self, keypair='@prompt', publishUpdates='true'):
        """
        Configure application to pass a Ravello "Key Pair" (ssh pubkey) to VM.
        
        This requires the VM has Cloud-Init installed.
        """
        keypair = self.ui_eval_param(keypair, 'string', '@prompt')
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        if self.confirm_app_is_published(quiet=True):
            # FIXME: We should be checking if the **VM** is published; not the app
            print(c.red("Cloud Init cannot be modified after VM is published!\n"))
            return
        keypairs = rCache.get_keypairs()
        kpNames = [kp['name'] for kp in keypairs]
        if keypair == '@prompt':
            print(c.BOLD("Keypairs available to you:"))
            for i, kp in enumerate(kpNames):
                print("  {})  {}".format(c.cyan(i), c.replace_bad_chars_with_underscores(kp)))
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter number of kp: "), endRange=i)
            kpName = keypair = kpNames[selection]
        elif keypair in [c.replace_bad_chars_with_underscores(k) for k in kpNames]:
            kpName = keypair
        else:
            print(c.red("Invalid keypair name! Use tab-completion or check /keypairs!\n"))
            return
        kpId = [kp['id'] for kp in keypairs if kp['name'] == kpName][0]
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if vm.get('keypairId', None) == kpId:
            print(c.yellow("No change was made! This VM is already set to use key pair '{}' with ID {}!".format(kpName, kpId)))
            return
        vm['keypairId'] = kpId
        vm['keypairName'] = rCache.get_keypair(kpId)['name']
        vm['supportsCloudInit'] = True
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_cloudinit_keypair(self, parameters, text, current_param):
        if current_param == 'keypair':
            kpNames = [c.replace_bad_chars_with_underscores(kp['name'])
                       for kp in rCache.get_keypairs()]
            completions = [a for a in kpNames
                           if a.startswith(text)]
        elif current_param == 'publishUpdates':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_cloudinit_userdata_from_file(self, inputFile, noconfirm='false',
            publishUpdates='true'):
        """
        Inject Cloud-Init user-data into VM from files.
        
        This requires the VM has Cloud-Init installed.
        
        *inputFile* must be the path to a file containing cloud-config data
        ("#cloud-config") or a shell script (e.g., "#!/bin/bash").
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        if self.confirm_app_is_published(quiet=True):
            # FIXME: We should be checking if the **VM** is published; not the app
            print(c.red("Cloud Init cannot be modified after VM is published!\n"))
            return
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if vm.get('userData', None):
            print(c.yellow("Warning: This VM is already has Cloud-Init userData in its design"))
            if not noconfirm:
                response = raw_input(c.CYAN("Continue with overwriting userData? [y/N] "))
                print()
                if response != 'y':
                    print("Leaving existing VM userData intact\n")
                    return
        try:
            with open(path.expanduser(inputFile)) as f:
                userData = f.read()
        except:
            print(c.RED("Problem reading inputFile '{}'!\n".format(inputFile)))
            raise
        vm['supportsCloudInit'] = True
        vm['userData'] = userData
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_cloudinit_userdata_from_file(self, parameters, text, current_param):
        if current_param == 'inputFile':
            return _complete_path(text)
        elif current_param in ['noconfirm', 'publishUpdates']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_nic_edit(self, index='@prompt', name='@current', mac='@current',
            deviceType='@current', bootProto='@current', ip='@current', mask='@current',
            gateway='@current', dns='@current', externalAccessState='@current',
            publishUpdates='true', forceRefresh='false'):
        """
        Edit an existing NIC in the VM design.
        
        All params (except *index*) allow a value of '@current' to make no change.
        
        *index* should be the index number of the existing NIC to edit
            (e.g., '0', '1')
        If specified, *mac* should be a valid hexadecimal MAC address with
            6 colon-separated octets
        If specified, *deviceType* should be one of:
            e1000
            virtio
            vmxnet3
            pcnet
            rtl8139
            ne2k_pci
            vmxnet
            e1000e
        If specified, *bootProto* should be either 'static' or 'dhcp'
        If specified, *ip* should be a valid decimal IP address with
            4 dot-separated octets
        When using bootProto=static, *gateway* and *dns* are optional and thus
            allow an an additional value of '@clear'; otherwise they should be
            valid decimal IP addresses with 4 dot-separated octets
        If specified, *externalAccessState* should be one of:
            CONDITIONAL_PUBLIC_IP
            ALWAYS_PUBLIC_IP
            ALWAYS_PORT_FORWARDING
        
        If application is already published, and *publishUpdates* is 'true'
        (default), the design changes will be immediately published to the
        cloud.
        
        The *forceRefresh* option disables the check that compares the NIC at
        the start with the NIC at the end, allowing to run, e.g.:
            nic_edit 0 forceRefresh=true
        This was added because we've run into situations where this cleared
        invalid design validation errors.
        
        Feel free to file RFEs for extra things that haven't been implemented.
        """
        index = self.ui_eval_param(index, 'string', '@prompt')
        name = self.ui_eval_param(name, 'string', '@current')
        mac = self.ui_eval_param(mac, 'string', '@current')
        deviceType = self.ui_eval_param(deviceType, 'string', '@current')
        bootProto = self.ui_eval_param(bootProto, 'string', '@current')
        ip = self.ui_eval_param(ip, 'string', '@current')
        mask = self.ui_eval_param(mask, 'string', '@current')
        gateway = self.ui_eval_param(gateway, 'string', '@current')
        dns = self.ui_eval_param(dns, 'string', '@current')
        externalAccessState = self.ui_eval_param(externalAccessState, 'string', '@current')
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        forceRefresh = self.ui_eval_param(forceRefresh, 'bool', False)
        print()
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if not vm.get('networkConnections'):
            print(c.red("This VM has no NICs!\n"))
            return
        nics = sorted(vm['networkConnections'], key=lambda nic: nic['device']['index'])
        # index
        if index == '@prompt':
            indices = []
            for n in nics:
                indices.append(n['name'])
            print(c.BOLD("Existing NICs on VM '{}':".format(self.vmName)))
            for i, name in enumerate(indices):
                print("  {})  {}".format(c.cyan(i), name))
            index = ui.prompt_for_number(c.CYAN("\nEnter number of nic: "), endRange=i)
        else:
            try:
                index = int(index)
            except:
                print(c.red("index must be a number!\n"))
                return
        try:
            nic = deepcopy(nics[index])
        except:
            print(c.red("Invalid nic number specified!\n"))
            return
        # name
        if name != '@current':
            nic['name'] = name
        # mac
        if mac != '@current':
            if not ui.validate_mac_addr(mac):
                print(c.red("Invalid MAC address format for mac!\n"))
                return
            nic['device']['useAutomaticMac'] = False
            nic['device']['mac'] = mac
        # deviceType
        if deviceType != '@current':
            if deviceType not in self.validNicDeviceTypes:
                print(c.red("Invalid deviceType! Must be one of: {}\n".format(", ".join(self.validNicDeviceTypes))))
                return
            nic['device']['deviceType'] = deviceType
        # bootProto
        if bootProto == '@current':
            if nic['ipConfig'].get('staticIpConfig'):
                bootProto = 'static'
            else:
                bootProto = 'dhcp'
        elif bootProto == 'static':
            try:
                del nic['ipConfig']['autoIpConfig']
                nic['ipConfig']['staticIpConfig'] = {}
            except:
                pass
        elif bootProto == 'dhcp':
            try:
                del nic['ipConfig']['staticIpConfig']
                nic['ipConfig']['autoIpConfig'] = {}
            except:
                pass
        # ip
        if ip == '@current':
            if bootProto == 'static':
                try:
                    nic['ipConfig']['staticIpConfig']['ip']
                except:
                    print(c.red("Must specify ip!\n"))
                    return
        elif bootProto == 'static':
            if not ui.validate_ipv4_addr(ip):
                print(c.red("Invalid IP format for ip!\n"))
                return
            nic['ipConfig']['staticIpConfig']['ip'] = ip
        else:
            print(c.red("Cannot specify ip when using bootProto=dhcp!\n"))
            return
        # mask
        if mask == '@current':
            if bootProto == 'static':
                try:
                    nic['ipConfig']['staticIpConfig']['mask']
                except:
                    print(c.red("Must specify mask!\n"))
                    return
        elif bootProto == 'static':
            if not ui.validate_ipv4_addr(mask):
                print(c.red("Invalid IP format for mask!\n"))
                return
            nic['ipConfig']['staticIpConfig']['mask'] = mask
        else:
            print(c.red("Cannot specify mask when using bootProto=dhcp!\n"))
            return
        # gateway
        if gateway == '@current':
            pass
        elif bootProto == 'static':
            if gateway == '@clear':
                try:
                    del nic['ipConfig']['staticIpConfig']['gateway']
                except:
                    pass
            else:
                if not ui.validate_ipv4_addr(gateway):
                    print(c.red("Invalid IP format for gateway!\n"))
                    return
                nic['ipConfig']['staticIpConfig']['gateway'] = gateway
        else:
            print(c.red("Cannot specify gateway when using bootProto=dhcp!\n"))
            return
        # dns
        if dns == '@current':
            pass
        elif bootProto == 'static':
            if dns == '@clear':
                try:
                    del nic['ipConfig']['staticIpConfig']['dns']
                except:
                    pass
            else:
                if not ui.validate_ipv4_addr(dns):
                    print(c.red("Invalid IP format for dns!\n"))
                    return
                nic['ipConfig']['staticIpConfig']['dns'] = dns
        else:
            print(c.red("Cannot specify dns when using bootProto=dhcp!\n"))
            return
        # externalAccessState
        if externalAccessState != '@current':
            if externalAccessState in ['CONDITIONAL_PUBLIC_IP', 'ALWAYS_PUBLIC_IP', 'ALWAYS_PORT_FORWARDING']:
                nic['ipConfig']['externalAccessState'] = externalAccessState
            else:
                print(c.red("Invalid externalAccessState!"))
                print("For valid choices, run command:")
                print(c.BOLD("    /apps/{}/vms/{} help nic_edit\n".format(self.appName, self.vmName)))
                return
        if nic == nics[index] and not forceRefresh:
            print(c.yellow("No changes were made to NIC!"))
            print("Use tab-completion to specify changes via cmdline args or run:")
            print(c.BOLD("    /apps/{}/vms/{} help nic_edit\n".format(self.appName, self.vmName)))
            return
        # Save changes back into vm object
        nics[index] = nic
        vm['networkConnections'] = nics
        self.update_vm(vm, publishUpdates)
    
    def update_vm(self, vm, publishUpdates=True):
        try:
            newVm = rClient.update_vm({'id': self.appId}, vm)
        except:
            print(c.red("Problem updating VM!\n"))
            raise
        rCache.purge_app_cache(self.appId)
        print(c.green("VM '{}' updated!".format(self.vmName)))
        if self.parent.parent.confirm_app_is_published(quiet=True):
            if publishUpdates:
                self.parent.parent.publish_design_updates()
            else:
                print(c.yellow("\nPublish your design updates to the cloud later by running:"))
                print(c.BOLD("    /apps/{}/ publish_design_updates\n".format(self.appName)))
        else:
            print()
    
    def ui_complete_nic_edit(self, parameters, text, current_param):
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        nics = vm.get('networkConnections', [])
        nics = sorted(nics, key=lambda nic: nic['device']['index'])
        try:
            nic = nics[int(parameters['index'])]
        except:
            nic = None
        if current_param == 'index':
            indices = [str(n) for n in range(len(nics))]
            indices.append('@prompt')
            completions = [a for a in indices
                           if a.startswith(text)]
        elif current_param  == 'name':
            names = ['@current']
            if nic:
                names.append(nic['name'])
            completions = [a for a in names
                           if a.startswith(text)]
        elif current_param == 'mac':
            macs = ['@current']
            if nic:
                macs.append(nic['device']['mac'])
            completions = [a for a in macs
                           if a.startswith(text)]
        elif current_param == 'deviceType':
            types = ['@current']
            types.extend(self.validNicDeviceTypes)
            completions = [a for a in types
                           if a.startswith(text)]
        elif current_param == 'bootProto':
            protos = ['@current', 'static', 'dhcp']
            completions = [a for a in protos
                           if a.startswith(text)]
        elif current_param == 'ip':
            ips = ['@current', '10.0.0.0', '192.168.0.0', '172.16.0.0']
            try:
                ips.append(nic['ipConfig']['staticIpConfig']['ip'])
            except:
                pass
            completions = [a for a in list(set(ips))
                           if a.startswith(text)]
        elif current_param == 'mask':
            masks = ['@current', '255.0.0.0', '255.255.0.0', '255.255.255.0']
            try:
                masks.append(nic['ipConfig']['staticIpConfig']['mask'])
            except:
                pass
            completions = [a for a in list(set(masks))
                           if a.startswith(text)]
        elif current_param == 'gateway':
            gws = ['@current', '@clear']
            try:
                gws.append(nic['ipConfig']['staticIpConfig']['gateway'])
            except:
                pass
            completions = [a for a in gws
                           if a.startswith(text)]
        elif current_param == 'dns':
            dns = ['@current', '@clear']
            try:
                dns.append(nic['ipConfig']['staticIpConfig']['dns'])
            except:
                pass
            completions = [a for a in dns
                           if a.startswith(text)]
        elif current_param == 'externalAccessState':
            states = ['@current', 'CONDITIONAL_PUBLIC_IP', 'ALWAYS_PUBLIC_IP', 'ALWAYS_PORT_FORWARDING']
            completions = [a for a in states
                           if a.startswith(text)]
        elif current_param in ['publishUpdates', 'forceRefresh']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_nic_add(self, index='@auto', name='@auto', publishUpdates='true'):
        """
        Add a new NIC to the VM design.
        
        The *index* controls whether to append the NIC to the end of the list
        of existing NICs or to insert it somewhere in the list. By default, the
        new NIC will get added to the end, so e.g., on a VM with 2 existing
        NICs (index 0 and index 1), the new NIC will be the 3rd and thus will
        get index 2. In the same situation, setting index=0 would insert the
        new NIC before the other two, changing their index numbers.
        
        *name* -- when not specified -- defaults to 'ethN' where N is the
        *index* number.
        
        On creation, the NIC's useAutomaticMac property is set to True and
        deviceType is set to virtio. All other values receive their default
        settings per the API (e.g., DHCP will be enabled & externalAccessState
        will be set to CONDITIONAL_PUBLIC_IP). Use the nic_edit command to make
        any customizations.
        
        If application is already published, and *publishUpdates* is 'true'
        (default), the design changes will be immediately published to the
        cloud.
        """
        index = self.ui_eval_param(index, 'string', '@auto')
        name = self.ui_eval_param(name, 'string', '@auto')
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if not vm.get('networkConnections'):
            vm['networkConnections'] = []
        nics = sorted(vm['networkConnections'], key=lambda nic: nic['device']['index'])
        if index == '@auto':
            # Append to end of list by default
            index = len(nics)
        else:
            valid = [str(n) for n in range(len(nics) + 1)]
            if index in valid:
                index = int(index)
            else:
                # If supplied index is invalid ...
                print(c.red("Invalid index number! Valid choices: {}\n".format(", ".join(valid))))
                return
        if name == '@auto':
            name = 'eth{}'.format(index)
        for n in range(len(nics)):
            if n >= index:
                nics[n]['device']['index'] += 1
        nic = {
            'name': name,
            'device': {
                'index': index,
                'deviceType': 'virtio',
                'useAutomaticMac': True
                }
            }
        nics.insert(index, nic)
        vm['networkConnections'] = nics
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_nic_add(self, parameters, text, current_param):
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if current_param == 'index':
            nics = vm.get('networkConnections', [])
            indices = [str(n) for n in range(len(nics) + 1)]
            indices.append('@auto')
            completions = [a for a in indices
                           if a.startswith(text)]
        elif current_param  == 'name':
            names = ['@auto']
            try:
                names.append('eth{}'.format(parameters['index']))
            except:
                pass
            completions = [a for a in names
                           if a.startswith(text)]
        elif current_param == 'publishUpdates':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_nic_delete(self, index, publishUpdates='true'):
        """
        Delete an existing NIC from the VM design.
        
        NICs are numbered by *index*, starting at zero.
        
        If application is already published, and *publishUpdates* is 'true'
        (default), the design changes will be immediately published to the
        cloud.
        """
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if not vm.get('networkConnections'):
            print(c.red("This VM has no NICs!\n"))
            return
        nics = sorted(vm['networkConnections'], key=lambda nic: nic['device']['index'])
        valid = [str(n) for n in range(len(nics))]
        if index in valid:
            index = int(index)
        else:
            print(c.red("Invalid index number! Valid choices: {}\n".format(", ".join(valid))))
            return
        for n in range(len(nics)):
            if n > index:
                nics[n]['device']['index'] -= 1
        del nics[index]
        vm['networkConnections'] = nics
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_nic_delete(self, parameters, text, current_param):
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if current_param == 'index':
            nics = vm.get('networkConnections', [])
            indices = [str(n) for n in range(len(nics))]
            completions = [a for a in indices
                           if a.startswith(text)]
        elif current_param == 'publishUpdates':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_nic_list(self):
        """
        List the NICs from the VM design.
        
        This command is a convenience function to show abbreviated info from
        the design aspect of a particular VM. To see full details about a VM,
        or to see deployment aspect (cloud) details, or to output to a file,
        use the print_def command.
        """
        print()
        vm = rCache.get_vm(self.appId, self.vmId, aspect='design')
        if not vm.get('networkConnections'):
            print(c.red("This VM has no NICs!\n"))
            return
        nics = sorted(vm['networkConnections'], key=lambda nic: nic['device']['index'])
        print(ui.prettify_json(nics))
        print()
    
    def ui_command_delete(self, noconfirm='false', publishUpdates='true'):
        """
        Delete a VM from the application design.

        If application is already published, and *publishUpdates* is 'true'
        (default), the design changes will be immediately published to the
        cloud.
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        if not noconfirm:
            c.slow_print(c.RED("Deleting a VM cannot be undone -- All VM data will be lost\n"))
            response = raw_input(c.CYAN("Continue with VM deletion? [y/N] "))
            print()
        if noconfirm or response == 'y':
            try:
                rClient.delete_vm_from_application(self.appId, self.vmId)
            except:
                print(c.red("Problem deleting VM!\n"))
                raise
            print(c.green("Deleted VM '{}'".format(self.vmName)))
            if self.parent.parent.confirm_app_is_published(quiet=True):
                if publishUpdates:
                    self.parent.parent.publish_design_updates()
                else:
                    print(c.yellow("\nPublish your design updates to the cloud later by running:"))
                    print(c.BOLD("    /apps/{}/ publish_design_updates\n".format(self.appName)))
            self.parent.remove_child(self)
            rCache.purge_app_cache(self.appId)
        else:
            print("Leaving VM intact\n")
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param in ['noconfirm', 'publishUpdates']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_update_from_file(self, inputFile, publishUpdates='true'):
        """
        Update a VM with design definition imported from json file.
        
        If application is already published, and *publishUpdates* is 'true'
        (default), the design changes will be immediately published to the
        cloud.
        """
        publishUpdates = self.ui_eval_param(publishUpdates, 'bool', True)
        print()
        try:
            with open(path.expanduser(inputFile)) as f:
                vm = json.load(f)
        except:
            print(c.red("Problem reading inputFile!\n"
                        "File should be a json VM design definition as generated by print_def cmd\n"))
            raise
        appId = vm.get('applicationId')
        if self.appId != appId:
            print(c.red("The 'applicationId' from the imported json does not match appId for this VM!\n"))
            return
        vmId = vm.get('id')
        if self.vmId != vmId:
            print(c.red("The 'id' from the imported json does not match vmId for this VM!\n"))
            return
        self.update_vm(vm, publishUpdates)
    
    def ui_complete_update_from_file(self, parameters, text, current_param):
        if current_param == 'inputFile':
            return _complete_path(text)
        elif current_param == 'publishUpdates':
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions


class Shared(ConfigNode):
    """Setup the 'shared' node.
    
    Path: /shared/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'shared', parent)
        self.isPopulated = False
        self.numberOfShares = 0
        self.nodeFromUser = {}
        self.nodeToTarget = {}
    
    def summary(self):
        if self.isPopulated:
            return ("{} sum total resources shared by everyone".format(self.numberOfShares), True)
        else:
            return ("To populate, run: refresh", False)
    
    def _integrate_share_into_node_structure(self, share):
        s = share
        self.numberOfShares += 1
        uid = int(s['sharingUserId'])
        child = self.nodeFromUser.get(uid)
        # Create child node if it doesn't exist
        if not child:
            child = self.nodeFromUser[uid] = SharedFromUser(uid, self)
        # Convert the targetEmail/communityId to a string
        if 'targetEmail' in s:
            target = s['targetEmail']
        elif 'targetCommunityId' in s:
            try:
                community = rClient.get_community(s['targetCommunityId'])
                target = community['name']
            except:
                target = "{}".format(s['targetCommunityId'])
        else:
            target = "NULL"
        if not self.nodeToTarget.get(uid):
            self.nodeToTarget[uid] = {}
        grandchild = self.nodeToTarget[uid].get(target)
        if not grandchild:
            grandchild = self.nodeToTarget[uid][target] = SharedToTarget(target, child)
        Share(s, grandchild)
    
    def refresh(self):
        self._children = set([])
        self.numberOfShares = 0
        self.nodeFromUser = {}
        self.nodeToTarget = {}
        rCache.update_share_cache()
        for s in rCache.get_shares():
            self._integrate_share_into_node_structure(s)
        self.isPopulated = True
    
    def ui_command_refresh(self):
        """
        Poll Ravello for list of shared resources.
        
        Not doing this automatically speeds startup time.
        """
        print(c.yellow("\nRefreshing all shared-resources data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))
    
    def _create_share(self, request):
        try:
            newShare = rClient.share_resource(request)
        except:
            print(c.red("\nProblem creating shared resource!\n"))
            raise
        print(c.green("\nShare created with share ID {}!\n".format(newShare['id'])))
        self._integrate_share_into_node_structure(newShare)
    
    def _new_share_helper(self, shareType, resource, email):
        if shareType == 'blueprint':
            data = rCache.get_bps(myOrgOnly=True)
            req = {'sharedResourceType': 'BLUEPRINT'}
        elif shareType == 'VM image':
            data = rClient.get_images()
            req = {'sharedResourceType': 'LIBRARY_VM'}
        elif shareType == 'disk image':
            data = rClient.get_diskimages()
            req = {'sharedResourceType': 'DISK_IMAGE'}
        allowed = []
        for j in data:
            allowed.append((j['name'], j['id']))
        if not allowed:
            print(c.red("\nThere are no {}s available for you to share!\n".format(shareType)))
            raise ValueError
        NAME = ID = None
        if resource == '@prompt':
            print(c.BOLD("\n{}s available to you:".format(shareType.title())))
            for i, r in enumerate(allowed):
                print("  {})  {}".format(c.cyan(i), r[0]))
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter number of {}: ".format(shareType)), endRange=i)
            NAME = allowed[selection][0]
            ID = allowed[selection][1]
        else:
            NAME = resource
        # Convert resource name to id if necessary
        if not ID:
            for r in allowed:
                if NAME == r[0]:
                    ID = r[1]
                    break
            else:
                # Quit if invalid resource name
                print(c.RED("\nInvalid {} name!\n".format(shareType)))
                raise ValueError
        req['sharedResourceId'] = ID
        if email == '@prompt':
            a = ''
            if not len(a):
                a = raw_input(c.CYAN("\nEnter target email address of user with which you want to share {}: ".format(shareType)))
            email = a
        req['targetEmail'] = email
        self._create_share(req)
    
    def ui_command_share_bp(self, blueprint='@prompt', targetEmail='@prompt'):
        """
        Create a new shared blueprint record.
        
        Optionally specify all parameters on the command-line.
        """
        blueprint = self.ui_eval_param(blueprint, 'string', '@prompt')
        targetEmail = self.ui_eval_param(targetEmail, 'string', '@prompt')
        self._new_share_helper(shareType='blueprint', resource=blueprint, email=targetEmail)
    
    def ui_complete_share_bp(self, parameters, text, current_param):
        if current_param == 'targetEmail':
            completions = [a for a in ['@prompt']
                           if a.startswith(text)]
        elif current_param == 'blueprint':
            allowedBlueprints = ['@prompt']
            for bp in rCache.get_bps(myOrgOnly=True):
                allowedBlueprints.append(bp['name'])
            completions = [a for a in allowedBlueprints
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_share_vm_image(self, image='@prompt', targetEmail='@prompt'):
        """
        Create a new shared VM image record.
        
        Optionally specify all parameters on the command-line.
        """
        image = self.ui_eval_param(image, 'string', '@prompt')
        targetEmail = self.ui_eval_param(targetEmail, 'string', '@prompt')
        self._new_share_helper(shareType='VM image', resource=image, email=targetEmail)
    
    def ui_complete_share_vm_image(self, parameters, text, current_param):
        if current_param == 'targetEmail':
            completions = [a for a in ['@prompt']
                           if a.startswith(text)]
        elif current_param == 'image':
            allowedImages = ['@prompt']
            for img in rClient.get_images():
                allowedImages.append(img['name'])
            completions = [a for a in allowedImages
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
        
    def ui_command_share_disk_image(self, image='@prompt', targetEmail='@prompt'):
        """
        Create a new shared disk image record.
        
        Optionally specify all parameters on the command-line.
        """
        image = self.ui_eval_param(image, 'string', '@prompt')
        targetEmail = self.ui_eval_param(targetEmail, 'string', '@prompt')
        self._new_share_helper(shareType='disk image', resource=image, email=targetEmail)
    
    def ui_complete_share_disk_image(self, parameters, text, current_param):
        if current_param == 'targetEmail':
            completions = [a for a in ['@prompt']
                           if a.startswith(text)]
        elif current_param == 'image':
            allowedImages = ['@prompt']
            for img in rClient.get_diskimages():
                allowedImages.append(img['name'])
            completions = [a for a in allowedImages
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions


class SharedFromUser(ConfigNode):
    """Setup the shared-from node.
    
    Path: /shared/BY_{USER_EMAIL}
    """
    
    def __init__(self, uid, parent):
        try:
            self.email = rCache.get_user(uid)['email']
            name = c.replace_bad_chars_with_underscores(self.email)
        except:
            self.email = "UNKNOWN UID {}".format(uid)
            name = "UID_{}".format(uid)
        self.name = "BY_{}".format(name)
        ConfigNode.__init__(self, self.name, parent)
        self.numberOfShares = self.numberOfTargets = 0
    
    def summary(self):
        targets = " to {} target".format(self.numberOfTargets)
        if not self.numberOfTargets:
            targets = ""
        elif self.numberOfTargets > 1:
            targets += "s"
        return ("{} resources shared by {}{}".format(self.numberOfShares, self.email, targets), True)


class SharedToTarget(ConfigNode):
    """Setup the shared-to node.
    
    Path: /shared/BY_{USER_EMAIL}/TO_{TARGET}/
    """
    
    def __init__(self, target, parent):
        self.target = target
        self.name = "TO_{}".format(c.replace_bad_chars_with_underscores(target))
        ConfigNode.__init__(self, self.name, parent)
        self.numberOfShares = 0
        parent.numberOfTargets += 1
    
    def summary(self):
        return ("{} shared to {}".format(self.numberOfShares, self.target), True)


class Share(ConfigNode):
    """Setup the dynamically-named share node.
    
    Path: /shared/BY_{USER_EMAIL}/TO_{TARGET}/{NAME}
    """
    
    def __init__(self, share, parent):
        s = share
        self.shareId = s['id']
        parent.numberOfShares += 1
        parent.parent.numberOfShares += 1
        resourceTypeShortener = {
            'BLUEPRINT': 'BP',
            'LIBRARY_VM': 'VM',
            'DISK_IMAGE': 'DISK',
            }
        # Shorten the resourceType
        self.resourceType = resourceTypeShortener[s['sharedResourceType']]
        # Translate resource ID into a name
        resId = s['sharedResourceId']
        if self.resourceType in 'BP':
            j = rCache.get_bp(resId)
        elif self.resourceType in 'VM':
            j = rClient.get_image(resId)
        elif self.resourceType in 'DISK':
            j = rClient.get_diskimage(resId)
        if j and 'name' in j:
            self.resource = '"{}"'.format(j['name'])
            self.name = c.replace_bad_chars_with_underscores(j['name'])
        else:
            self.resource = "ID {}".format(resId)
            self.name = c.replace_bad_chars_with_underscores(self.resource)
        ConfigNode.__init__(self, self.name, parent)
        # Convert timestamp to date
        self.date = ui.convert_ts_to_date(s['time'], showHours=False)
        # Compose it all together
        self.status = "{resourceType} {resource} on {date}".format(
            resourceType=self.resourceType,
            resource=self.resource,
            date=self.date)

    def summary(self):
        return (self.status, None)
    
    def ui_command_print_def(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON definition of shared resource.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "share definition for {} {} (/shared/{}/{}/{})".format(
            self.resourceType, self.resource, self.parent.parent.name, self.parent.name, self.name)
        ui.print_obj(rCache.get_share(self.shareId), description, outputFile,
            tmpPrefix='share_{}_{}'.format(self.resourceType, self.shareId))
        
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []
    
    def delete(self):
        try:
            rClient.delete_share(self.shareId)
        except:
            print(c.red("Problem deleting share!\n"))
            raise
        print(c.green("Deleted share {}\n".format(self.shareId)))
        rCache.purge_share_cache(self.shareId)
        self.parent.parent.parent.numberOfShares -= 1
        self.parent.parent.numberOfShares -= 1
        self.parent.numberOfShares -= 1
        if not self.parent.parent.numberOfShares:
            # If the sharing user has no more shares, remove everything
            rootNode.get_child('shared').remove_child(self.parent.parent)
        elif not self.parent.numberOfShares:
            # Or if theere are no more resources shared TO the same target, remove that
            self.parent.parent.remove_child(self.parent)
        else:
            # Otherwise, just remove ourself
            self.parent.remove_child(self)
    
    def ui_command_delete(self, noconfirm='false'):
        """
        Delete a share.
        
        By default, confirmation will be required to delete the share.
        Disable prompt with noconfirm=true.
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        print()
        if not noconfirm:
            response = raw_input(c.CYAN("Continue with share deletion? [y/N] "))
            print()
        if noconfirm or response == 'y':
            self.delete()
        else:
            print("Leaving share intact\n")
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param in ['noconfirm']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions

class Keypairs(ConfigNode):
    """Setup the 'keypairs' node.
    
    Path: /keypairs/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'keypairs', parent)
        self.isPopulated = False
        self.numberOfKps = 0
    
    def summary(self):
        if self.isPopulated:
            return ("{} keypairs".format(self.numberOfKps), None)
        else:
            return ("To populate, run: refresh", False)
    
    def refresh(self):
        self._children = set([])
        self.numberOfKps = 0
        rCache.purge_keypair_cache()
        for kp in rCache.get_keypairs():
            Keypair(kp, self)
        self.isPopulated = True
    
    def ui_command_refresh(self):
        """
        Poll Ravello for list of key pairs.
        
        Not doing this automatically speeds startup time.
        """
        print(c.yellow("\nRefreshing all key pairs data . . . "), end='')
        stdout.flush()
        self.refresh()
        print(c.green("DONE!\n"))
    
    def ui_command_upload_new_pubkey(self, inputFile='@prompt', name='@prompt'):
        """
        Upload a new public key to the account.
        
        By specifying *inputFile* on the command-line, you can use a full path,
        i.e., choices are not restricted to ~/.ssh dir.
        
        Optionally specify *name* on the command-line to avoid prompting.
        """
        inputFile = self.ui_eval_param(inputFile, 'string', '@prompt')
        name = self.ui_eval_param(name, 'string', '@prompt')
        if inputFile == '@prompt':
            print()
            sshPubKeys = glob(path.expanduser('~/.ssh/') + 'id_*.pub')
            if not len(sshPubKeys):
                print(c.red("There are not any 'id_*.pub' files in your ~/.ssh directory!\n"))
                print("To upload an ssh pubkey file from some other location, pass it as an argument"
                      "to this command, e.g.: `{}`\n"
                      .format(c.BOLD('/keypairs upload_new_pubkey /path/to/file')))
                return
            # Enumerate through list of files
            print(c.BOLD("Available public key files in ~/.ssh:"))
            for i, key in enumerate(sshPubKeys):
                print("  {})  {}".format(c.cyan(i), key))
            # Prompt for pubkey selection
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter the number of the pubkey file you wish to upload: "),
                endRange=i)
            inputFile = sshPubKeys[selection]
        try:
            with open(path.expanduser(inputFile)) as f:
                pubkeyData = f.read()
        except:
            print(c.RED("Problem reading pubkey file '{}'!\n".format(inputFile)))
            raise
        if name == '@prompt':
            name = raw_input(c.CYAN("\nEnter a unique name for your new public key: "))
            if len(name):
                if any(name == k['name'] for k in rCache.get_keypairs()):
                    print(c.red("\nA key by that name already exists in your account!\n"))
                    return
            else:
                print(c.red("\nYou must enter a name!\n"))
                return
        req = {'name': name, 'publicKey': pubkeyData.strip()}
        try:
            kp = rClient.create_keypair(req)
        except:
            print(c.red("\nProblem uploading new public key!\n"))
            raise
        print(c.green("\nSUCCESS! New public key '{}' ({}) uploaded!".format(kp['name'], kp['id'])))
        rCache.purge_keypair_cache()
        Keypair(kp, self)
        print()
    
    def ui_complete_upload_new_pubkey(self, parameters, text, current_param):
        if current_param == 'inputFile':
            return _complete_path(text)
        else:
            return []


class Keypair(ConfigNode):
    """Setup the dynamically-named keypair node.
    
    Path: /keypairs/{NAME}/
    """
    
    def __init__(self, kp, parent):
        self.kpString = c.replace_bad_chars_with_underscores(kp['name'])
        ConfigNode.__init__(self, self.kpString, parent)
        parent.numberOfKps += 1
        self.kp = kp
        if 'creator' in kp:
            user = kp['creator']['nickname']
        else:
            user = "(NULL)"
        if 'creationTime' in kp:
            _date = ui.convert_ts_to_date(kp['creationTime'], showHours=False)
        else:
            _date = "(NULL)"
        self.status = "'{name}' ({id}) created by {user} on {date}".format(
            name=kp['name'],
            id=kp['id'],
            user=user,
            date=_date)
    
    def summary(self):
        return (self.status, None)
    
    def ui_command_print_def(self, outputFile='@EDITOR'):
        """
        Pretty-print JSON definition of public key.
        
        Note: unfortunately the API doesn't return actual public key data.
        
        Optionally specify *outputFile* as @term or @pager or as a relative /
        absolute path on the local system (tab-completion available). Default
        value of '@EDITOR' checks environment for a RAVSH_EDITOR variable, and
        failing that, EDITOR, and failing that, it falls back to gvim, then
        vim, then less.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@EDITOR')
        description = "key pair definition for '{}' (/keypairs/{})".format(
            self.kp['name'], self.kp['id'])
        ui.print_obj(self.kp, description, outputFile,
            tmpPrefix='keypair_{}'.format(self.kp['id']))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param == 'outputFile':
            return _complete_path(text)
        else:
            return []
    
    def delete(self):
        try:
            rClient.delete_keypair(self.kp['id'])
        except:
            print(c.red("Problem deleting public key!\n"))
            raise
        self.parent.numberOfKps -= 1
        rCache.purge_keypair_cache(self.kp['id'])
        print(c.green("Deleted public key '{}' ({})\n".format(self.kp['name'], self.kp['id'])))
        self.parent.remove_child(self)
    
    def ui_command_delete(self, noconfirm='false'):
        """
        Delete a public key.
        
        By default, confirmation will be required to delete the key.
        Disable prompt with noconfirm=true.
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        print()
        if not noconfirm:
            print(c.yellow("This will delete the '{}' public key from your account in Ravello"
                           .format(self.kp['name'])))
            response = raw_input(c.CYAN("Continue with key deletion? [y/N] "))
            print()
        if noconfirm or response == 'y':
            self.delete()
        else:
            print("Leaving key pair intact\n")
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param in ['noconfirm']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_rename(self, name='@prompt'):
        """
        Rename a public key.
        """
        name = self.ui_eval_param(name, 'string', '@prompt')
        if name == '@prompt':
            name = raw_input(c.CYAN("\nEnter a new unique name for your public key: "))
            if len(name):
                if any(name == k['name'] for k in rClient.get_keypairs()):
                    print(c.red("\nA key by that name already exists in your account!\n"))
                    return
            else:
                print(c.red("\nYou must enter a name!\n"))
                return
        req = {'name': name, 'id': self.kp['id']}
        try:
            kp = rClient.update_keypair(req)
        except:
            print(c.red("\nProblem renaming public key!\n"))
            raise
        print(c.green("\nSUCCESS! Public key {} renamed from '{}' to '{}'!".format(self.kp['id'], self.kp['name'], kp['name'])))
        rCache.purge_keypair_cache(self.kp['id'])
        Keypair(kp, self.parent)
        self.parent.remove_child(self)
        print()
