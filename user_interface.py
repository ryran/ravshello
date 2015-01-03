# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

from __future__ import print_function

# Modules from standard library
import json
import subprocess
import termios
import re
from sys import stdout, stdin
from pydoc import pager
from time import sleep, time
from os import path, makedirs, chmod, remove
from datetime import datetime, date
from getpass import getpass
from calendar import month_name
from operator import itemgetter

# Modules not from standard library, but widely available
try:
    from configshell import shell as cfshell, ConfigNode
except:
    print("Missing a required python module (configshell)\n"
          "On RHEL/Fedora, install it with command:\n"
          "                        yum install python-configshell\n")
    raise
# Remove configshell commands that we don't need or want
del ConfigNode.ui_command_pwd
del ConfigNode.ui_command_bookmarks
del ConfigNode.ui_complete_bookmarks

# Custom ravshello modules
import rsaw_ascii
try:
    from ravello_sdk import *
except:
    print("Missing a required python module (ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk\n")
    raise
from local_config import RavshelloUI 


cfgFile = RavshelloUI()
ravshOpt = c = user = ravClient = appnamePrefix = None
appCache = {}
alertCache = {}
userCache = {}


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


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None, confirm=False):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    pwd1 = getpass(prompt=prompt)
    while not len(pwd1):
        if defaultPass:
            return defaultPass
        else:
            print("You must enter a passphrase")
            pwd1 = getpass(prompt=prompt)
    if confirm:
        print("Re-enter pass to confirm")
        pwd2 = getpass(prompt=prompt)
        while not pwd1 == pwd2:
            print("Second passphrase did not match the first!")
            pwd2 = getpass(prompt=prompt)
    return pwd1


def main(opt, client):
    # Set some important globals
    global ravshOpt, ravClient, user, appnamePrefix, c
    ravshOpt = opt
    ravClient = client
    user = ravshOpt.user
    appnamePrefix = 'k:' + user + '__'
    c = rsaw_ascii.AsciiColors(ravshOpt.enableAsciiColors)
    
    # Clear preferences if asked via cmdline arg
    if ravshOpt.clearPreferences:
        remove(path.join(ravshOpt.userCfgDir, 'prefs.bin'))
    
    # Read configfile and override user defaults
    shell = cfshell.ConfigShell(ravshOpt.userCfgDir)
    shell.prefs['color_mode'] = True
    shell.prefs['tree_max_depth'] = 1
    shell.prefs['prompt_length'] = 0
    shell.prefs['tree_show_root'] = True
    shell.prefs['tree_status_mode'] = True
    if not ravshOpt.enableAsciiColors:
        shell.prefs['color_mode'] = False
    if not ravshOpt.showAllApps:
        # Turn off max depth restriction for admins in restricted-view mode
        shell.prefs['tree_max_depth'] = 0

    verbose("  Fetching data from Ravello . . . ", end='')
    stdout.flush()
    # Start configshell
    try:
        root_node = RavelloRoot(shell)
    except:
        print()
        print(c.RED("  UNHANDLED EXCEPTION getting data from Ravello"))
        print("\nIf problem persists, send this message with below traceback to rsaw@redhat.com")
        raise
    verbose("Done!")
    
    print()
    
    if is_admin() and ravshOpt.cmdlineArgs:
        if ravshOpt.scriptFile:
            print(c.yellow("Ignoring script file because cmdline args present\n"))
        shell.run_cmdline(ravshOpt.cmdlineArgs)
    
    elif is_admin() and ravshOpt.scriptFile:
        try:
            shell.run_script(ravshOpt.scriptFile)
        except:
            print(c.red("Unable to open script file\n"))
    
    elif is_admin():
        shell.run_interactive()
    
    else:
        if ravshOpt.cmdlineArgs or ravshOpt.scriptFile:
            print(c.red("Sorry! Only admins are allowed to use ravshello non-interactively\n"))
            return
        try:
            # Plan was to flush sys.stdin with this, per
            # http://abelbeck.wordpress.com/2013/08/29/clear-sys-stdin-buffer/
            # It always throws exception though, so I decided to just use it to quit
            termios.tcflush(stdin, termios.TCIOFLUSH)
        except:
            print(c.red("Sorry! Only admins are allowed to use ravshello non-interactively\n"))
            return
        # Initial usage hints
        print(c.BOLD("Instructions:"))
        print(" ┐")
        print(" │ NAVIGATE: Use `{}` and `{}` with tab-completion".format(c.BOLD('cd'), c.BOLD('ls')))
        print(" │ COMMANDS: Use tab-completion to see commands specific to each dir")
        print(" │ GET HELP: Use `{}`".format(c.BOLD('help')))
        print(" │")
        print(" │ Your first time?")
        print(" │   - First: use `{}` command".format(c.BOLD('cd apps')))
        print(" │   - Next: press TAB-TAB to see available commands")
        print(" │   - Next: use `{}` command to get started".format(c.BOLD('create_app')))
        print(" │   - Optional: `{}` into new app directory and press TAB-TAB to see commands".format(c.BOLD('cd')))
        print(" │   - Optional: use `{}` command to add an hour to the timer".format(c.BOLD('extend_app_autostop')))
        print(" └──────────────────────────────────────────────────────────────────────────────")
        print()
        shell.run_interactive()


def monthdelta(date, delta):
    m, y = (date.month+delta) % 12, date.year + ((date.month)+delta-1) // 12
    if not m: m = 12
    d = min(date.day, [31,
        29 if y%4==0 and not y%400==0 else 28,31,30,31,30,31,31,30,31,30,31][m-1])
    return date.replace(day=d,month=m, year=y)

def prepare_file_for_writing(filePath, overwrite=True):
    d = path.dirname(filePath)
    if len(d) and not path.exists(d):
        try:
            makedirs(d, 0775)
        except OSError as e:
            print(c.RED("Unable to create dir '{}' for output file!\n"
                        "  {}\n".format(d, e)))
            raise
    if not overwrite and path.exists(filePath):
        print(c.red("Warning: output file already exists!\n"))
        response = raw_input(c.CYAN("Are you sure you want to overwrite file? [y/N] "))
        print()
        if not response == 'y':
            print("Good choice. That file looks important.\n")
            raise Exception

def slow_print(string, interval=.02):
    for char in string:
        sleep(interval)
        print(char, end='')
        stdout.flush()
    print()

def replace_bad_chars_with_underscores(string):
    """Perform some simple character translation/substitution on *string*."""
    return string.replace('@', '_').replace(' ', '_').replace('+', '_')

def sync_file_with_str(outfile, string, perms=0600):
    """Save *string* to *outfile*"""
    try:
        with open(outfile, 'w') as f:
            f.write(str(string))
        chmod(outfile, perms)
    except:
        pass

def prompt_for_number(prompt, endRange=None, startRange=0, defaultNumber=None):
    """Prompt for + require a positive natural number or a number in a range."""
    while True:
        try:
            if defaultNumber is None:
                n = int(raw_input(prompt))
            else:
                n = raw_input(prompt)
                if len(n):
                    n = int(n)
                else:
                    n = int(defaultNumber)
            if endRange > 0:
                r = range(startRange, endRange + 1)
                if n in r:
                    break
            else:
                if n > 0:
                    break
            raise ValueError
        except ValueError:
            print("Not a valid number! Try again")
    return n

def prettify_json(input):
    """Convert dictionary-like json to multiline indented output."""
    return str(json.dumps(input, indent=4))

def iterate_json_keys_for_value(jsonObj, key, value):
    """Return True if *jsonObj* contains a key *key* set to value *value*."""
    for i in jsonObj:
        if i[key] == value:
            return True
    return False

def get_learner_active_vms(learner):
    """Return the number of active VMs a learner has."""
    activeVms = 0
    for app in ravClient.get_applications(filter={'published': True}):
        if is_admin() and ravshOpt.showAllApps or app['name'].startswith(appnamePrefix):
            try:
                activeVms += app['deployment']['totalActiveVms']
            except:
                pass
    return activeVms

def check_timestamp_proximity(timeStamp, thresholdMins=1):
    m, s = divmod(time() - timeStamp, 60)
    if m < thresholdMins:
        return True
    return False

def update_app_cache(appId=None):
    global appCache
    if appId:
        appCache[appId] = {}
        appCache[appId]['definition'] = ravClient.get_application(appId)
        appCache[appId]['ts'] = time()
    else:
        for appId in appCache:
            try:
                 a = ravClient.get_application(appId)
            except:
                continue
            appCache[appId] = {}
            appCache[appId]['definition'] = a
            appCache[appId]['ts'] = time()

def purge_app_cache(appId=None):
    global appCache
    if appId:
        if appId in appCache:
            del appCache[appId]
    else:
        appCache = {}

def get_app(appId):
    if appId in appCache and check_timestamp_proximity(appCache[appId]['ts'], 1):
        pass
    else:
        update_app_cache(appId)
    return appCache[appId]['definition']

def update_user_cache():
    global userCache
    userCache = {}
    for u in ravClient.get_users():
        userCache[u['id']] = u
    userCache['_timestamp'] = time()

def purge_user_cache():
    global userCache
    userCache = {}

def get_user(userId):
    if userId in userCache and check_timestamp_proximity(userCache['_timestamp'], 1):
        pass
    else:
        update_user_cache()
    return userCache[userId]

def update_alert_cache():
    global alertCache
    alertCache = {}
    for a in ravClient.get_alerts():
        try:
            alertCache[a['eventName']].append(
                {'userId': a['userId'], 'alertId': a['id']})
        except:
            try:
                alertCache[a['eventName']] = [
                    {'userId': a['userId'], 'alertId': a['id']}]
            except:
                print("This should never happen!")
                raise
    alertCache['_timestamp'] = time()

def purge_alert_cache():
    global alertCache
    alertCache = {}

def get_alerts_for_event(eventName):
    global alertCache
    if not len(alertCache):
        update_alert_cache()
    if eventName in alertCache and check_timestamp_proximity(alertCache['_timestamp'], 5):
        return alertCache[eventName]
    else:
        return None

def get_application_details(app):
    """Return VM details for application with ID *app*."""
    if isinstance(app, dict): app = app['id']
    appDefinition = ravClient.get_application(app)
    if not appDefinition['published']:
        return None, None, None, None
    vmDetails = []
    for vm in appDefinition['deployment']['vms']:
        vmDict = {
            'name': vm['name'],
            'state': vm['state'],
            'exPorts': [],
            'ssh': {'fqdn': '', 'port': ''},
            'vnc': '',
            'ipAddrs': [],
            'hostnames': []
        }
        try:
            for service in vm['suppliedServices']:
                if service['external'] == True:
                    if service['name'] == 'ssh':
                        vmDict['ssh']['port'] = ' -p ' + service['externalPort']
                    if not service['name'].startswith('dummy'):
                        vmDict['exPorts'].append(
                            service['externalPort'] + "/{}".format(service['protocol']))
        except:
            pass
        try:
            for interface in vm['networkConnections']:
                vmDict['ipAddrs'].append(
                    "{} ({})".format(interface['ipConfig']['staticIpConfig']['ip'], interface['name']))
        except:
            pass
        try:
            vmDict['ssh']['fqdn'] = vm['externalFqdn']
        except:
            pass
        try:
            vmDict['vnc'] = ravClient.get_vnc_url(app, vm['id'])
        except:
            pass
        try:
            vmDict['hostnames'] = vm['hostnames']
        except:
            pass
        vmDetails.append(vmDict)
        try:
            expirationTime = appDefinition['deployment']['expirationTime']
        except:
            expirationTime = None
    return vmDetails, appDefinition['deployment']['cloud'], appDefinition['deployment']['regionName'], expirationTime



class RavelloRoot(ConfigNode):
    """Setup the Ravello root node where anything is possible.
    Path: /
    """
    
    def __init__(self, shell):
        ConfigNode.__init__(self, '/', shell=shell)
        if is_admin():
            Blueprints(self)
            Billing(self)
            Users(self)
            Monitoring(self)
            Events(self)
            # Images(self)
        Applications(self)
    
    
    def summary(self):
        if is_admin():
            status = "Local admin user: {}, Ravello user: {}".format(user, ravClient._username)
        else:
            status = "Logged in as user: {}".format(user)
        return (status, None)



class Events(ConfigNode):
    """Setup the 'events' node.
    Path: /events/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'events', parent)
        self.isPopulated = False
    
    
    def summary(self):
        if self.isPopulated:
            return ("{} possible events".format(self.numberOfEvents), None)
        else:
            return ("To populate, run command: refresh_events", False)
        
        
    def refresh(self):
        self._children = set([])
        update_user_cache()
        self.numberOfEvents = 0
        for eventName in ravClient.get_events():
            Event("%s" % eventName.swapcase(), self)
            self.numberOfEvents += 1
        self.isPopulated = True
    
    def ui_command_refresh_events(self):
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
              prettify_json(ravClient.get_events()))
    
    
    def ui_command_print_event_names(self, outputFile='@pager'):
        """
        Pretty-print JSON list of Ravello event names in pager or export to file.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        
        Alerts can be registered for any of the returned event names with the
        register_alert command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_event_names()
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(ravClient.get_events(), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing event names\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Exported event names to file: '{}'\n".format(outputFile)))
    
    
    def print_registered_alerts(self):
        pager("JSON list of REGISTERED USER ALERTS\n" +
              prettify_json(ravClient.get_alerts()))
    
    
    def ui_command_print_registered_alerts(self, outputFile='@pager'):
        """
        Pretty-print JSON list of userAlerts registered.
        
        Assuming the current Ravello user is an admin, they will actually see
        all alerts in the organization.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        
        Create alerts with the register_alert command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_registered_alerts()
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(ravClient.get_alerts(), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing userAlerts\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Exported userAlerts to file: '{}'\n".format(outputFile)))



class Event(ConfigNode):
    """Setup the dynamically-named event node.
    Path: /events/{EVENT_NAME}/
    """
    
    def __init__(self, eventName, parent):
        ConfigNode.__init__(self, eventName, parent)
        self.eventName = eventName.swapcase()
        self.refresh()
    
    
    def refresh(self):
        self._children = set([])
        eventAlerts = get_alerts_for_event(self.eventName)
        if eventAlerts:
            for a in eventAlerts:
                UserAlert(
                    "{}-{}".format(userCache[a['userId']]['email'].split('@')[0].split('+')[0], a['userId']),
                    self,
                    a['alertId'],
                    a['userId'])
    
    
    def summary(self):
        eventAlerts = get_alerts_for_event(self.eventName)
        if eventAlerts:
            return ("Alerts registered", True)
        else:
            return ("No alerts", False)
    
    
    def ui_command_register_alert(self, userEmail='@moi'):
        """
        Register the currently logged-in Ravello user to receive email on event.
        
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
            for userId in userCache:
                if userCache[userId]['email'] == userEmail:
                    userId = userCache[userId]['id']
                    break
            else:
                print(c.RED("No Ravello user on your account with that email!\n"))
                return
        print(c.yellow("Attempting to register alert . . . "), end='')
        stdout.flush()
        try:
            ravClient.create_alert(self.eventName, userId)
        except:
            print(c.red("\n\nProblem registering alert!\n"))
            raise
        print(c.green("DONE!\n"))
        purge_alert_cache()
        self.refresh()



class UserAlert(ConfigNode):
    """Setup the dynamically-named user alert node.
    Path: /events/{EVENT_NAME}/{USER_IDENTIFIER}/
    """
    
    def __init__(self, userString, parent, alertId, userId):
        ConfigNode.__init__(self, userString, parent)
        self.userId = userId
        self.alertId = alertId
    
    
    #~ def summary(self):
        #~ return (get_user(self.userId)['email'], None)
    
    
    def ui_command_unregister_alert(self):
        """
        Delete a previously-registered alert.
        """
        print()
        print(c.yellow("Attempting to unregister alert . . . "), end='')
        stdout.flush()
        try:
            ravClient.delete_alert(self.alertId)
        except:
            print(c.red("\n\nProblem unregistering alert!\n"))
            raise
        print(c.green("DONE!\n"))
        purge_alert_cache()
        self.parent.remove_child(self)



class Monitoring(ConfigNode):
    """Setup the 'monitoring' node.
    Path: /monitoring/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'monitoring', parent)
    
    
    def summary(self):
        return ("Ready for queries", None)
    
    
    def daily_activity_summary(self, output='@stdout', day=date.today().day, month=date.today().month, year=date.today().year):
        """
        Print a report of account activity for the current day.
        
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
    
    
    def ui_command_search_notifications(self, appId=None, maxResults=500, notificationLevel=None, startTime=None, endTime=None, outputFile='@pager'):
        """
        Pretty-print JSON list of notification search results in pager or
        export to file.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        
        Results will be returned in reverse chronological order with
        newest matches at the top.
        
        To see details about a specific application only, determine appId first,
        e.g., with print_app_definition command.
        
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
        This ravshello function compensates for you by appending 3 zeroes to the
        end of any number you pass (so basically, don't worry about it).
        """
        print()
        maxResults = self.ui_eval_param(maxResults, 'number', 500)
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        #~ appId = self.ui_eval_param(appId, 'number', None)
        #~ notificationLevel = self.ui_eval_param(notificationLevel, 'string', 'INFO')
        if isinstance(startTime, int): startTime=int(str(startTime) + '000')
        if isinstance(endTime, int): endTime=int(str(endTime) + '000')
        req = {'maxResults': maxResults, 'appId': appId,
               'notificationLevel': notificationLevel,
               'dateRange': {'startTime': startTime, 'endTime': endTime}}

        if outputFile == '@pager':
            pager("NOTIFICATION SEARCH RESULTS\n" +
                  prettify_json(ravClient.search_notifications(req)))
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(ravClient.search_notifications(req), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing notification search results\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Exported notification search results to file: '{}'\n".format(outputFile)))



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
            x = monthdelta(date.today(), -1)
            month = x.month
            year = x.year
            month = prompt_for_number(c.CYAN("Enter month by number [{}]: ".format(month)),
                                      startRange=1, endRange=12,
                                      defaultNumber=month)
            print()
        else:
            try:
                month = int(month)
                if month == 0:
                    month = date.today().month
                elif month < 0:
                    x = monthdelta(date.today(), month)
                    month = x.month
                    year = x.year
                else:
                    j = month_name[month]
            except:
                print(c.RED("Invalid month specification!\n"))
                raise
        return month, year
    
    
    def ui_command_inspect_all_charges(self, outputFile='@pager', month='@prompt', year=date.today().year):
        """
        Print full JSON for all charges in a specific month.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        
        Optionally specify month to avoid being prompted.
        Setting month to 0 is the same as specifying the number of the current
        month. Specifying a negative number for month will cause year
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The year can only be specified as an absolute (positive) number.
        
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        month = self.ui_eval_param(month, 'string', '@prompt')
        year = self.ui_eval_param(year, 'number', date.today().year)
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
            
        print(c.yellow("Pulling summary of charges for {}-{} . . .\n"
                       .format(year, month_name[month])))
        try:
            b = ravClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        
        if outputFile == '@pager':
            pager("Full details of charges incurred for all apps since beginning of the month\n" + 
                  prettify_json(b))
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(b, f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing billing information!\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Wrote billing information to file: '{}'".format(outputFile)))
        print()
    
    
    def ui_command_this_months_summary(self, sortBy='kerb'):
        """
        Print billing summary of all charges since beginning of this month.
        
        With sortBy, charges can be sorted by Ravello acct user ('rav') or
        kerberos user ('kerb').
        """
        print()
        sortBy = self.ui_eval_param(sortBy, 'string', 'kerb')
        if not sortBy in 'rav' and not sortBy in 'kerb':
            print(c.RED("Specify sortBy as 'rav' or 'kerb'\n"))
            return
        print(c.yellow("Pulling summary of charges since the start of this month . . .\n"))
        try:
            b = ravClient.get_billing()
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        print("Note: data could be up to 1 hour old\n")
        self.process_billing(b, sortBy)
        print()
    
    
    def ui_command_select_month_summary(self, month='@prompt', year=date.today().year, sortBy='kerb'):
        """
        Print billing summary of all charges in a specific month.
        
        Setting month to 0 is the same as specifying the number of the current
        month. Specifying a negative number for month will cause year
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The year can only be specified as an absolute (positive) number.
        
        With sortBy, charges can be sorted by Ravello acct user ('rav') or
        kerberos user ('kerb'), with the latter being the default.
        """
        print()
        month = self.ui_eval_param(month, 'string', '@prompt')
        year = self.ui_eval_param(year, 'number', date.today().year)
        sortBy = self.ui_eval_param(sortBy, 'string', 'kerb')
        if not sortBy in 'rav' and not sortBy in 'kerb':
            print(c.RED("Specify sortBy as 'rav' or 'kerb'\n"))
            return
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
        print(c.yellow("Pulling summary of charges for {}-{} . . .\n"
                       .format(year, month_name[month])))
        try:
            b = ravClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        self.process_billing(b, sortBy)
        print()
    
    
    def process_billing(self, monthsCharges, sortBy):
        
        appsByUser = {}
        chargesByProduct = {}
        
        for app in monthsCharges:
            
            try:
                appName = app['appName']
            except:
                appName = 'UNDEFINED'
            
            if sortBy in 'rav':
                try:
                    user = app['owner']['email']
                except:
                    user = 'ORG (not associated with specific apps)'
            else:
                if appName.startswith('k:'):
                    user, appName = appName.split('__', 1)
                    user = user.split(':')[1]
                else:
                    user = 'APPS THAT DON\'T FOLLOW KERBEROS NAMING SCHEME'
            
            if user not in appsByUser:
                appsByUser[user] = []
            
            totalCharges = 0
            
            for prod in app['charges']:
                
                try:
                    totalCharges += prod['summaryPrice']
                except:
                    pass
                
                prodName = prod['productName'].replace('Performance Opt', 'Perf-Opt').replace('Cost Opt', 'Cost-Opt')
                
                if prodName not in chargesByProduct:
                    chargesByProduct[prodName] = {
                        'summaryPrice': 0,
                        'productRate': prod['productRate'],
                        'unitName': prod['unitName']}
                
                chargesByProduct[prodName]['summaryPrice'] += prod['summaryPrice']
            
            try:
                creationTime = int(str(app['creationTime'])[:-3])
            except:
                creationTime = 0
            
            appsByUser[user].append({'appName': appName,
                                     'totalCharges': totalCharges,
                                     'creationTime': creationTime})
        
        acctGrandTotal = 0
        
        for user in appsByUser:
            
            userGrandTotal = 0
            
            print(c.BLUE("{}:".format(user)))
            print(c.magenta("    Charges\tCreation Time\tApplication Name"))
            
            for a in sorted(appsByUser[user], key=itemgetter('creationTime')):
                
                tc = a['totalCharges']
                userGrandTotal += tc
                if tc < 5:
                    tc = c.green("${:7.2f}".format(tc))
                elif tc < 15:
                    tc = c.yellow("${:7.2f}".format(tc))
                elif tc < 25:
                    tc = c.YELLOW("${:7.2f}".format(tc))
                elif tc < 35:
                    tc = c.red("${:7.2f}".format(tc))
                else:
                    tc = c.RED("${:7.2f}".format(tc))
                
                if not a['creationTime']:
                    creationTime = 'UNDEFINED'
                else:
                    creationTime = datetime.fromtimestamp(a['creationTime']).strftime('%m/%d @ %H:%M')
                
                print("    {}\t{}\t{}"
                      .format(tc, creationTime, a['appName']))
            
            acctGrandTotal += userGrandTotal
            
            if not a['totalCharges'] == userGrandTotal:
                print("    --------")
                print("    " + c.REVERSE("${:7.2f}".format(userGrandTotal)))
            print()
            
        prodGrandTotal = 0
        
        print(c.BLUE("\nCharges by product:"))
        print(c.magenta("    Charges\tUnit Price\tCount\tProduct Name"))
        
        for prod in sorted(chargesByProduct):
            
            tc = chargesByProduct[prod]['summaryPrice']
            prodGrandTotal += tc
            if tc < 15:
                tc = c.green("${:7.2f}".format(tc))
            elif tc < 50:
                tc = c.yellow("${:7.2f}".format(tc))
            elif tc < 90:
                tc = c.YELLOW("${:7.2f}".format(tc))
            elif tc < 130:
                tc = c.red("${:7.2f}".format(tc))
            else:
                tc = c.RED("${:7.2f}".format(tc))
            
            print("    {}\t".format(tc) +
                  "${:.2f} {}\t"
                  .format(chargesByProduct[prod]['productRate'],
                          chargesByProduct[prod]['unitName'].replace('Hour', 'Hr').replace('Month', 'Mo')) +
                  "{:5.1f}\t".format(chargesByProduct[prod]['summaryPrice'] / chargesByProduct[prod]['productRate']) +
                  "{}".format(prod))
        
        print("    --------\n    "  + 
              c.REVERSE("${:7.2f}\tMonthly charges grand total".format(prodGrandTotal)))



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
            return ("To populate, run command: refresh_users", False)
    
    
    def refresh(self):
        self._children = set([])
        self.numberOfUsers = self.numberOfAdmins = 0
        update_user_cache()
        for userId in userCache:
            if not userId == '_timestamp':
                User("{}-{}".format(userCache[userId]['email'].split('@')[0].split('+')[0], userId),
                     self,
                     userId)
                self.numberOfUsers += 1
                if 'ADMIN' in userCache[userId]['roles']:
                    self.numberOfAdmins += 1
        self.isPopulated = True
    
    
    def ui_command_refresh_users(self):
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
    
    
    def ui_command_invite_new_user(self):
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
            user = ravClient.create_user(req)
        except:
            print(c.red("Problem inviting user\n!"))
            raise
        self.numberOfUsers += 1
        print(c.green("Invited user {}\n".format(req['email'])))
        User("%s" % user['email'], self, user['id'])



class User(ConfigNode):
    """Setup the dynamically-named user node.
    Path: /users/{USER_EMAIL}/
    """
    
    def __init__(self, user, parent, userId):
        ConfigNode.__init__(self, user, parent)
        self.userId = userId
    
    
    def summary(self):
        user = get_user(self.userId)
        if 'ADMIN' in user['roles']:
            r = True
        else:
            r = None
        return (user['email'], r)
    
    
    def ui_command_get_user_info(self):
        """
        Pretty-print user details.
        
        Borrrrrrring.
        """
        print()
        print(prettify_json(get_user(self.userId)))
        print()
    
    
    def ui_command_update_user_info(self):
        """
        Update user first/last name and admin status.
        """
        
        user = ravClient.get_user(self.userId)
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
        req = {'email': user['email'], 'name': name,  'surname': surname, 'roles': user['roles']}
        try:
            userCache[user['id']] = ravClient.update_user(req, user['id'])
        except:
            print(c.red("Problem updating user!\n"))
            raise
        
        if minusAdmin:
            self.parent.numberOfAdmins -= 1
        elif addAdmin:
            self.parent.numberOfAdmins += 1
        print(c.green("Updated user info\n"))
    
    
    def ui_command_delete_user(self):
        """
        Delete a user.
        
        Hopefully very carefully. No confirm option for this one.
        """
        print()
        slow_print(c.bgRED("  W A R N I N G ! ! ! !"))
        slow_print(c.RED("\nPress Ctrl-c now unless you are ABSOLUTELY SURE you want to delete {}'s account!"
                         .format(self.userEmail)))
        slow_print(c.RED("ARE YOU POSITIVELY CONFIDENT THAT ALL THIS USER'S APPS & VMS SHOULD BE DESTROYED?"))
        response = raw_input(c.CYAN("\nType 'yes!' in ALL CAPS to continue: "))
        print()
        if response == 'YES!':
            if 'ADMIN' in get_user(self.userId)['roles']:
                admin = True
            else:
                admin = False
            try:
                ravClient.delete_user(self.userId)
            except:
                print(c.red("Problem deleting user!\n"))
                raise
            self.parent.numberOfUsers -= 1
            if admin:
                self.parent.numberOfAdmins -= 1
            print(c.green("Deleted user {}\n".format(self.userEmail)))
            self.parent.remove_child(self)
        else:
            print("Leaving user intact (probably a good choice)\n")
    
    
    def ui_command_change_user_password(self):
        """
        Change a user's password.
        
        Doing this requires entering the current password.
        """
        req = {}
        req['existingPassword'] = get_passphrase(c.CYAN("\nEnter {}'s current password: ".format(self.userEmail)))
        print()
        req['newPassword'] = get_passphrase(c.CYAN("Enter new password: "), confirm=True)
        print()
        try:
            ravClient.changepw_user(req, self.userId)
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
            return ("{} blueprints".format(self.numberOfBps), None)
        else:
            return ("To populate, run command: refresh_blueprints", False)
    
    def refresh(self):
        self._children = set([])
        self.numberOfBps = 0
        for bp in ravClient.get_blueprints():
            Bp("%s" % bp['name'], self, bp['id'], bp['creationTime'])
            self.numberOfBps += 1
        self.isPopulated = True
    
    
    def ui_command_refresh_blueprints(self):
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
    
    
    def ui_command_backup_all_bps(self, bpDir='@home'):
        """
        Export each & every blueprint to a JSON file.
        
        Default bpDir of @home maps to ~/.ravshello/blueprints. Optionally
        specify an absolute or relative path.
        
        File names are determined automatically from the blueprint name (plus an
        extension of ".json"). Existing files are overwritten.
        """
        print()
        bpDir = self.ui_eval_param(bpDir, 'string', '@home')
        if bpDir == '@home':
            bpDir = path.join(ravshOpt.userCfgDir, 'blueprints')
        bpDir = path.expanduser(bpDir)
        if not path.exists(bpDir):
            try:
                makedirs(bpDir, 0775)
            except OSError as e:
                print(c.RED("Error creating bpDir!\n  {}\n".format(e)))
                return
        elif not path.isdir(bpDir):
            print(c.RED("Error! Specified bpDir '{}' already exists as a regular file!\n"
                        .format(bpDir)))
            return
        for bp in ravClient.get_blueprints():
            f = path.join(bpDir, bp['name'] + '.json')
            try:
                with open(f, 'w') as outfile:
                    json.dump(ravClient.get_blueprint(bp['id']), outfile, indent=4)
            except IOError as e:
                print(c.red("Problem exporting bp '{}'\n  {}".format(bp['name'], e)))
                continue
            print(c.green("Exported bp to file: '{}'".format(f)))
        print()
    
    
    def create_bp_from_json_obj(self, bpDefinition, bpFileName=None):
        """Create a new blueprint from a json blueprint defition."""
        
        def _delete_temporary_app(appId, appName):
            try:
                ravClient.delete_application(newApp['id'])
            except:
                print("\nNotice: Unable to delete temporary unpublished application '{}'\n" 
                      .format(appName))
        
        # Set default bp name from bp json or filename
        # Set default description different depending on whether bp created from file or existing bp
        if not bpFileName:
            # Generate a new blueprint name suggestion based off current one
            bpName = new_name(ravClient.get_blueprints(), bpDefinition['name'] + '_')
            bpDescription = "Created by {} as a copy of blueprint '{}'".format(user, bpDefinition['name'])
        else:
            bpName = path.basename(bpFileName)
            bpDescription = "Created by {} from blueprint file '{}'".format(user, bpName)
        
        # Prompt for a blueprint name
        b = raw_input(c.CYAN("\nEnter a unique name for your new blueprint [{}]: ".format(bpName.strip('.json'))))
        if len(b): bpName = b
        
        # Create temporary application from bp
        appName = appnamePrefix + 'BpTempApp'
        appName = new_name(ravClient.get_applications(), appName + '_')
        appDescription = "Temporary app used to restore blueprint from file"
        appDesign = bpDefinition['design']
        appReq = {'name' : appName, 'description' : appDescription, 'design': appDesign}
        try:
            newApp = ravClient.create_application(appReq)
        except:
            print(c.red("\nUnable to create temporary application '{}'! "
                        "Cannot continue with restore!\n".format(appName)))
            raise
        
        # Prompt for description
        d = raw_input(c.CYAN("\nOptionally enter a description for your new blueprint [{}]: ".format(bpDescription)))
        if len(d): bpDescription = d
        
        # Create request dictionary and post new bp
        req = {"applicationId": newApp['id'], "blueprintName": bpName, "offline": "true", "description": bpDescription}
        try:
            newBp = ravClient.create_blueprint(req)
        except:
            print(c.red("\nProblem creating new blueprint!\n"))
            _delete_temporary_app(newApp['id'], appName)
            raise
        print(c.green("\nSUCCESS! New blueprint created!"))
        
        # Delete temp app
        _delete_temporary_app(newApp['id'], appName)

        # Add new bp to directory tree                                                                       
        Bp("%s" % newBp['name'], self, newBp['id'], newBp['creationTime'])
        
        # View new blueprint?
        response = raw_input(c.CYAN("\nView new blueprint definition? [y/N] "))
        if response == 'y':
            self.get_child(bpName).print_bp_definition()
        print()
    
        
    def ui_command_create_bp_from_file(self, inputFile='@prompt'):
        """
        Create a blurprint from JSON file in ~/.ravshello/blueprints.
        
        By specifying inputFile on the command-line, you can use a full path,
        i.e., choices are not restricted to ~/.ravshello/blueprints.
        
        This command is only useful after running one of the following:
            - backup_all_bps
            - backup_bp
            - print_bp_definition outputFile=PATH
        """
        inputFile = self.ui_eval_param(inputFile, 'string', '@prompt')
        if inputFile == '@prompt':
            print()
            # Get a list of what is in local cache
            c1 = subprocess.Popen(['ls', path.join(ravshOpt.userCfgDir, 'blueprints')],
                                  stdout=subprocess.PIPE)
            bpFileList = c1.communicate()[0].strip('\n').split('\n')
            bpFileList = filter(None, bpFileList)
            if not len(bpFileList):
                print(c.red("There are not any blueprint files in your local cache ({})!\n"
                            .format(path.join(ravshOpt.userCfgDir, 'blueprints'))))
                print("(They would need to have been created by the `{}`, `{}`, or `{}` commands)\n"
                      .format(c.BOLD('backup_all_bps'), c.BOLD('backup_bp'), c.BOLD('print_bp_definition')))
                return
            
            # Enumerate through list of files
            print(c.BOLD("Blueprint json definitions available in {}:"
                       .format(path.join(ravshOpt.userCfgDir, 'blueprints'))))
            for i, bp in enumerate(bpFileList):
                print("  {})  {}".format(c.cyan(i), bp))
            
            # Prompt for bp selection
            selection = prompt_for_number(c.CYAN("\nEnter the number of a file you wish to create a new blueprint from: "), i)
            inputFile = path.join(ravshOpt.userCfgDir, 'blueprints', bpFileList[selection])
        
        # Load chosen blueprint def file into json obj
        try:
            with open(inputFile) as f:
                bpDefinition = json.load(f)
        except:
            print(c.RED("Problem importing json data from file!\n"))
            raise
        
        # Make the magic happen
        self.create_bp_from_json_obj(bpDefinition, inputFile)



class Bp(ConfigNode):
    """Setup the dynamically-named blueprint node.
    Path: /blueprints/{BLUEPRINT_NAME}/
    """
    
    def __init__(self, name, parent, bpId, creationTime):
        ConfigNode.__init__(self, name, parent)
        self.bpId = bpId
        self.bpName = name
        self.creationTime = datetime.fromtimestamp(int(str(creationTime)[:-3]))
    
    
    def summary(self):
        if self.creationTime.year == datetime.now().year:
            if (self.creationTime.month == datetime.now().month and
                self.creationTime.day == datetime.now().day):
                    created = self.creationTime.strftime('today @ %H:%M')
            else:
                created = self.creationTime.strftime('%m/%d')
        else:
            created = self.creationTime.strftime('%Y/%m/%d')
        return ("Created: {}".format(created), None)
    
    
    def delete_bp(self):
        try:
            ravClient.delete_blueprint(self.bpId)
        except:
            print(c.red("Problem deleting blueprint!\n"))
            raise
        print(c.green("Deleted blueprint {}\n".format(self.bpName)))
        self.parent.remove_child(self)
    
    
    def ui_command_delete_bp(self, confirm='true', backupB4del='true'):
        """
        Delete a blueprint.
        
        By default, blueprint will automatically be saved to
        ~/.ravshello/blueprints/<BlueprintName>.json, overwriting any existing
        file. Disable with backupB4del=false.
        
        By default, confirmation will be required to delete the blueprint.
        Disable prompt with confirm=false.
        """
        backupB4del = self.ui_eval_param(backupB4del, 'bool', True)
        confirm = self.ui_eval_param(confirm, 'bool', True)
        print()
        if backupB4del:
            print("Backing up blueprint definition to local file before deleting . . .")
            self.ui_command_backup_bp()
            print("Blueprint can be recreated from file later with {} command\n"
                  .format(c.BOLD("restore_bp_from_file")))
        if confirm:
            slow_print(c.RED("Deleting a blueprint cannot be undone -- make sure you know what you're doing\n"))
            response = raw_input(c.CYAN("Continue with blueprint deletion? [y/N] "))
            print()
        if not confirm or response == 'y':
            self.delete_bp()
        else:
            print("Leaving bp intact (probably a good choice)\n")
    
    
    def ui_command_find_bp_publish_locations(self):
        """
        Print details about available publish locations for a blueprint.
        """
        print()
        pager("Blueprint available publish locations for '{}'\n".format(self.bpName) + 
              prettify_json(ravClient.get_blueprint_publish_locations(self.bpId)))
    
    
    def print_bp_definition(self):
        pager("JSON definition for BLUEPRINT '{}'\n".format(self.bpName) + 
              prettify_json(ravClient.get_blueprint(self.bpId)))
    
    
    def ui_command_print_bp_definition(self, outputFile='@pager'):
        """
        Pretty-print blueprint JSON in pager or export to outputFile.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_bp_definition()
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(ravClient.get_blueprint(self.bpId), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing bp definition for '{}'\n"
                            "{}\n".format(self.bpName, e)))
                return
            print(c.green("Exported bp definition to file: '{}'\n".format(outputFile)))
    
    
    def ui_command_backup_bp(self):
        """
        Export blueprint XML and store to a JSON file in ~/.ravshello/blueprints.
        
        File names are determined automatically from the blueprint name (plus an
        extension of ".json"). Existing files are overwritten.
        """
        print()
        d = path.join(ravshOpt.userCfgDir, 'blueprints')
        if not path.exists(d):
            makedirs(d, 0775)
        f = path.join(d, self.bpName + '.json')
        try:
            with open(f, 'w') as outfile:
                json.dump(ravClient.get_blueprint(self.bpId), outfile, indent=4)
        except:
            print(c.red("Problem exporting bp '{}'".format(self.bpName)))
            raise
        print(c.green("Exported bp to file: '{}'\n".format(f)))
    
    
    def ui_command_make_bp_copy(self):
        """Create a copy of an existing blueprint."""
        # Get current blueprint def
        bpDefinition = ravClient.get_blueprint(self.bpId)
        # Make the magic happen
        self.parent.create_bp_from_json_obj(bpDefinition)



class Applications(ConfigNode):
    """Setup the 'applications' node.
    Path: /apps/
    """
    
    def __init__(self, parent):
        ConfigNode.__init__(self, 'apps', parent)
        self.refresh()
    
    
    def refresh(self):
        purge_app_cache()
        self._children = set([])
        self.numberOfApps = self.numberOfPublishedApps = 0
        for app in ravClient.get_applications():
            if is_admin() and ravshOpt.showAllApps:
                App("%s" % app['name'], self, app['id'])
                self.numberOfApps += 1
                if app['published']: self.numberOfPublishedApps += 1
            else:
                if app['name'].startswith(appnamePrefix):
                    App("%s" % app['name'].replace(appnamePrefix, ''),
                        self, app['id'])
                    self.numberOfApps += 1
                    if app['published']: self.numberOfPublishedApps += 1
    
    
    def summary(self):
        totalActiveVms = get_learner_active_vms(user)
        if not self.numberOfApps:
            return ("No applications", False)
        return ("{} active VMs, {} of {} applications published"
                .format(totalActiveVms, self.numberOfPublishedApps, self.numberOfApps), None)
        
                                   
    def ui_command_refresh_apps(self):
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
    
    
    def ui_command__DELETE_ALL_APPS_(self, confirm='true'):
        """
        Deletes all user applications.
        
        Allows deleting all apps associated with your username.
        Use confirm=false with care.
        """
        print()
        if is_admin() and ravshOpt.showAllApps:
            print(c.red("NOPE!\n"
                        "The delete-all-apps cmd doesn't work when logged in as admin with visibility to all apps\n"))
            print("Log out and use -a/--admin instead of -A/--allapps\n"
                  "That will allow you to quickly delete all apps that include your kerberos in their name\n")
            return
        confirm = self.ui_eval_param(confirm, 'bool', True)
        if confirm:
            slow_print(c.bgRED("  W A R N I N G ! ! ! !"))
            slow_print(c.RED("\nPress Ctrl-c now unless you are ABSOLUTELY SURE you want to delete all of your applications!"))
            slow_print(c.RED("ARE YOU POSITIVELY CONFIDENT THAT ALL OF YOUR VMs SHOULD BE DESTROYED?"))
            response = raw_input(c.CYAN("\nType 'yes!' in ALL CAPS to continue: "))
            print()
        if not confirm or response == 'YES!':
            purge_app_cache()
            for app in ravClient.get_applications():
                if app['name'].startswith(appnamePrefix):
                    appName = app['name'].replace(appnamePrefix, '')
                    try:
                        self.get_child(appName).delete_app()
                    except:
                        print(c.yellow("\nThere is a new application available to you since you started ravshello!"))
                        print("To avoid deleting an app you cannot see, we've refreshed the apps for you ..." +
                              "You'll now need to re-run this command\n")
                        return
            self.refresh()
        else:
            print("Whew! That was close! Leaving your apps alone sounds like a good idea")
        print()
    
    def ui_command_create_app(self, blueprint='@prompt', name='@prompt', desc='@prompt', publish='true', region='@prompt', startAllVms='true'):
        """
        Interactively create a new application from a base blueprint.
        
        Optionally specify all parameters on the command-line.
        Note that application name, desc, region can be set to '@auto'.
        If run with publish=false, the publish_app command can be run later.
        """
        blueprint = self.ui_eval_param(blueprint, 'string', '@prompt')
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        publish = self.ui_eval_param(publish, 'bool', True)
        region = self.ui_eval_param(region, 'string', '@prompt')
        startAllVms = self.ui_eval_param(startAllVms, 'bool', True)
        startAllVms = self.ui_type_bool(startAllVms, reverse=True)
        
        # Check for available blueprints first
        allowedBlueprints = []
        blueprints = ravClient.get_blueprints()
        for bp in blueprints:
            try:
                description = bp['description']
            except:
                description = ''
            if is_admin() or any(tag in description for tag in ravshOpt.learnerBlueprintTag) or '#k:' + user in description:
                allowedBlueprints.append(bp['name'])
        if not allowedBlueprints:
            print(c.red("\nThere are no blueprints available for you to base an application on!\n"
                        "Contact an admin like ablum or rsaw"))
            return
        
        if blueprint == '@prompt':
            # Print available blueprints
            print(c.BOLD("\nBlueprints available to you:"))
            for i, bp in enumerate(allowedBlueprints):
                print("  {})  {}".format(c.cyan(i), bp))
            
            # Prompt for blueprint selection
            selection = prompt_for_number(c.CYAN("\nEnter number of blueprint: "), i)
            baseBlueprintName = allowedBlueprints[selection]
        else:
            baseBlueprintName = blueprint
            
        # Quit if invalid blueprint name
        if baseBlueprintName not in allowedBlueprints or not iterate_json_keys_for_value(blueprints, 'name', baseBlueprintName):
            print(c.RED("\nInvalid blueprint name!\n"))
            return
        
        # Convert blueprint name to id
        for bp in blueprints:
            if bp['name'] == baseBlueprintName:
                baseBlueprintId = bp['id']
                break
        
        if name == '@prompt' or name == '@auto':
            # Set default app name based off blueprint name
            appName = replace_bad_chars_with_underscores(baseBlueprintName)
            
            if is_admin() and name == '@prompt':
                # Prompt for name if admin
                a = raw_input(c.CYAN("\nEnter a name for your new application [{}]: ".format(appName)))
                if len(a):
                    if ' ' in a or '@' in a or '+' in a:
                        print(c.red("\nNote that ravshello has trouble navigating to directories with spaces, @ and + signs\n"
                                    "In order to do so, one would have to use the *interactive* cd command with arrow keys"))
                        response = raw_input(c.CYAN("\nReplace bad characters with underscores? [y/N] "))
                        if response == 'y':
                            a = replace_bad_chars_with_underscores(a)
                    appName = a
        else:
            appName = name
            
        appName = appnamePrefix + appName
        
        # Ensure there's not already an app with that name
        appName = new_name(ravClient.get_applications(), appName + '_')            
        
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
            
        appDesc += "[Created with ravshello {} by k:{}]".format(ravshOpt.ravshelloVersion.split()[1], user)
        
        # Build request dictionary
        req = {'name' : appName, 'description' : appDesc, 'baseBlueprintId': baseBlueprintId}
        
        # Attempt create request!
        try:
            newApp = ravClient.create_application(req)
        except:
            print(c.red("\nProblem creating application!\n"))
            raise
        
        self.numberOfApps += 1
        
        # Strip appname prefix for purposes of our UI
        if not ravshOpt.showAllApps:
            appName = appName.replace(appnamePrefix, '')
        
        print(c.green("\nApplication '{}' created!".format(appName)))
        
        # Add new app to directory tree
        App("%s" % appName, self, newApp['id'])
        
        if publish:
            self.get_child(appName).ui_command_publish_app(region, startAllVms)
        else:
            print()



class App(ConfigNode):
    """Setup the dynamically-named app node.
    Path: /apps/{APP_NAME}/
    """
    
    def __init__(self, name, parent, appId):
        ConfigNode.__init__(self, name, parent)
        self.appId = appId
        self.appName = name
        Vms(self)
    
    
    def summary(self):
        app = get_app(self.appId)
        if app['published']:
            cloud = app['deployment']['cloud']
            region = app['deployment']['regionName']
            totalErrorVms = app['deployment']['totalErrorVms']
            appState = application_state(app)
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
            currentDescription = app['description']
            m = re.search('_{(.*)}_', currentDescription)
            if m:
                note = '; ' + m.group(1)
            else:
                note = ''
            return ("{} in {} {}{}".format(appState, cloud, region, note), hazHappy)
        else:
            return ("Unpublished draft", None)
    
    
    def print_message_app_not_published(self):
        print(c.red("Application has not been published yet!\n"))
        print("To publish application, run command:")
        print(c.BOLD("    /apps/{}/ publish_app\n".format(self.appName)))
    
    
    def confirm_app_is_published(self):
        update_app_cache(self.appId)
        if not get_app(self.appId)['published']:
            self.print_message_app_not_published()
            return False
        return True
    
    
    def ui_command_update_app_note(self, note='@prompt'):
        """
        Embed an arbitrary string of text in the application description.
        
        Things to keep in mind:
        
        - In Ravello, app descriptions are limited to 255 bytes
        
        - All applications created by ravshello get something like the following
          stored as their initial description:
          
            [Created with ravshello v1.0.1 by k:rsawhill]
            
        - When using this command, ravshello keeps the above-mentioned string
          intact if it is already present, meaning that notes created by this
          command could be limited to around ~200 bytes
          
        - When specifying the note non-interactively with note=<SomeNoteHere>,
          you cannot use spaces (bummer limitation of configShell!)
        """
        print()
        note = self.ui_eval_param(note, 'string', '@prompt')
        
        if note == '@prompt':
            print(c.BOLD("With this command you can store an arbitrarily free-form note about this app"))
            print("(For example, to keep track of learning module progress)\n")
        
        app = ravClient.get_application(self.appId)
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
            ravClient.update_application(app)
        except:
            print(c.red("\n\nProblem updating application!\n"))
            raise
        print(c.green("Done!\n"))
        purge_app_cache(self.appId)
        
        if note == '@prompt':
            print("Notes can be seen with the {} command\n"
                  .format(c.BOLD("ls")))
        
        
    def ui_command_loop_query_app_status(self, desiredState=None, intervalSec=20, totalMin=30):
        """
        Execute query_app_status command on a loop.
        
        Optionally specify desiredState -- loop ends if all VMs reach this state.
        Optionally specify loop interval in seconds.
        Optionally specify total loop time in minutes.
        """
        desiredState = self.ui_eval_param(desiredState, 'string', 'None')
        intervalSec = self.ui_eval_param(intervalSec, 'number', 20)
        totalMin = self.ui_eval_param(totalMin, 'number', 30)
        if not is_admin():
            if intervalSec < 5:
                print(c.red("\nUsing minimum learner interval of 5 sec"))
                intervalSec = 5
            if totalMin > 65:
                print(c.red("\nUsing maximum learner watch-time of 65 min"))
                totalMin = 65
            elif totalMin < 1:
                print(c.red("\nUsing minimum learner watch-time of 1 min"))
                totalMin = 1
        self.loop_query_app_status(desiredState, intervalSec, totalMin)
    
    
    def loop_query_app_status(self, desiredState=None, intervalSec=20, totalMin=30):
        maxLoops = totalMin * 60 / intervalSec
        print(c.yellow("\nPolling application every {} secs for next {} mins to display VM status . . ."
              .format(intervalSec, totalMin)))
        if desiredState:
            print("Will stop polling when all VMs reach '{}' state"
                  .format(desiredState))
        print("(Cancel at any time with " + c.BOLD("Ctrl-c") + ")\n")
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
            allVmsStarted, allVmsStopped = self.query_app_status()
            if desiredState == 'STARTED':
                if allVmsStarted is True: break
            if desiredState == 'STOPPED':
                if allVmsStopped is True: break
            loopCount += 1
        print(c.green("All VMs reached '{}' state!\n".format(desiredState)))
    
    
    def ui_command_query_app_status(self):
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
        self.query_app_status()
    
    
    def query_app_status(self):
        vmDetails, cloudProvider, regionName, expireTime = get_application_details(self.appId)
        if not vmDetails:
            self.print_message_app_not_published()
            return None, None
        # Defaults
        allVmsAreStarted = True
        allVmsAreStopped = True
        key = ''
        if cfgFile.sshKeyFile:
            key = ' -i ' + cfgFile.sshKeyFile
        if expireTime:
            # Prepare expiration times
            absoluteExpireTime = int(str(expireTime)[:-3])
            m, s = divmod(absoluteExpireTime - time(), 60)
            absoluteExpireTime = datetime.fromtimestamp(absoluteExpireTime)
            if m > 0:
                t = "{:.0f}:{:02.0f}".format(m, s)
                if m <= 4:
                    t = c.bgRED(t)
                elif m <= 15:
                    t = c.RED(t)
                elif m <= 30:
                    t = c.YELLOW(t)
                else:
                    t = c.GREEN(t)
                autoStopMessage = c.BOLD("will auto-stop in {}".format(t)) + c.BOLD(" min at {}".format(absoluteExpireTime.strftime('%H:%M:%S')))
            else:
                autoStopMessage = c.BOLD("were auto-stopped on {}".format(absoluteExpireTime.strftime('%Y/%m/%d @ %H:%M')))
        else:
            autoStopMessage = c.BOLD("never had auto-stop set")
        # Print
        print(c.BOLD("App VMs in {} ({}) ".format(cloudProvider, regionName)) + autoStopMessage)
        print()
        for vm in vmDetails:
            ssh = vnc = None
            # Set ssh command
            if vm['ssh']['fqdn']:
                ssh = c.cyan("ssh{}{} root@{}".format(key, vm['ssh']['port'], vm['ssh']['fqdn']))
            # Set VNC url
            if vm['vnc']:
                vnc = c.blue(vm['vnc'])
            # Set variables for return
            if vm['state'] not in 'STARTED':
                allVmsAreStarted = False
            if vm['state'] not in 'STOPPED':
                allVmsAreStopped = False
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
            # Start printing
            print("  {}".format(c.BOLD(vm['name'])))
            print("     State:              {}".format(state))
            if vm['state'] in 'STARTED' or vm['state'] in 'STOPPING' or vm['state'] in 'RESTARTING':
                if vm['hostnames']:
                    print("     Internal DNS Name:  ", end="")
                    print(*vm['hostnames'], sep=', ')
                if vm['ipAddrs']:
                    print("     Internal IPs:       ", end="")
                    print(*vm['ipAddrs'], sep=', ')
                if vm['exPorts']:
                    print("     External Ports:     ", end="")
                    print(*vm['exPorts'], sep=', ')
                if vm['state'] not in 'STARTING':
                    if ssh:
                        print("     SSH Command:        {}".format(ssh))
                    if vnc:
                        print("     VNC Web URL:        {}".format(vnc))
            print()
        return allVmsAreStarted, allVmsAreStopped
    
    
    def extend_app_autostop(self, minutes=65):
        if not self.confirm_app_is_published():
            return False
        req = {'expirationFromNowSeconds' : minutes * 60}
        try:
            ravClient.set_application_expiration(self.appId, req)
        except:
            print(c.red("\nProblem setting application auto-stop!"))
            return
        print(c.green("\nApp auto-stop set for {} minutes from now"
                      .format(minutes)))
        purge_app_cache(self.appId)
    
    
    def ui_command_extend_app_autostop(self, minutes=65):
        """
        Set the application auto-stop time in minutes.
        
        Learners can only set auto-stop from 0 up to the default of 65 min.
        Admins can set any value, including '-1' which disables auto-stop timer.
        """
        minutes = self.ui_eval_param(minutes, 'number', 65)
        if not is_admin():
            if minutes > 65:
                print(c.red("\nUsing maximum learner auto-stop time of 65 minutes"))
                minutes = 65
            elif minutes < 0:
                print(c.RED("\nInvalid learner auto-stop time\n"))
                return
        self.extend_app_autostop(minutes)
        print()
    
    
    def print_app_definition(self):
        pager("JSON definition for APPLICATION '{}'\n".format(self.appName) + 
              prettify_json(ravClient.get_application(self.appId)))
    
    
    def ui_command_print_app_definition(self, outputFile='@pager'):
        """
        Pretty-print app JSON in pager or export to outputFile.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_app_definition()
        else:
            try:
                prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(ravClient.get_application(self.appId), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing app definition for '{}'\n"
                            "  {}\n".format(self.appName, e)))
                return
            print(c.green("Exported app definition to file: '{}'\n".format(outputFile)))
    
    
    def delete_app(self):
        if get_app(self.appId)['published']:
            published = True
        else:
            published = False
        try:
            ravClient.delete_application(self.appId)
        except:
            print(c.red("Problem deleting app!\n"))
            raise
        if published:
            self.parent.numberOfPublishedApps -= 1
        self.parent.numberOfApps -= 1
        print(c.green("Deleted application {}".format(self.appName)))
        self.parent.remove_child(self)
    
    
    def ui_command_delete_app(self, confirm='true'):
        """
        Delete an application.
        
        By default, confirmation will be required to delete the application.
        Disable prompt with confirm=false.
        """
        confirm = self.ui_eval_param(confirm, 'bool', True)
        print()
        if confirm:
            slow_print(c.RED("Deleting an application cannot be undone -- All VM data will be lost\n"))
            response = raw_input(c.CYAN("Continue? [y/N] "))
            print()
        if not confirm or response == 'y':
            self.delete_app()
        else:
            print("Leaving app intact (probably a good choice)")
        print()
    
    
    def ui_command_publish_app(self, region='@prompt', startAllVms='true'):
        """
        Interactively publish an application to the cloud.
        
        Optionally specify a region and whether all VMs should be started after
        publishing.
        """
        region = self.ui_eval_param(region, 'string', '@prompt')
        startAllVms = self.ui_eval_param(startAllVms, 'bool', True)
        
        # Sanity check
        if get_app(self.appId)['published'] is True:
            print(c.red("\nApplication already published!\n"))
            return
        
        # Set defaults
        selection = preferredCloud = preferredRegion = None
        
        if not is_admin():
            # Check that we don't have more published apps than we should
            totalActiveVms = get_learner_active_vms(user)
            if self.parent.numberOfPublishedApps >= ravshOpt.maxLearnerPublishedApps:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of published apps!"
                            .format(ravshOpt.maxLearnerPublishedApps)))
                print("Delete an app and try running command:")
                print(c.BOLD("    /apps/{}/ publish_app\n".format(self.appName)))
                return
            elif totalActiveVms >= ravshOpt.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!"
                            .format(ravshOpt.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try running command:")
                print(c.BOLD("    /apps/{}/ start_app\n".format(self.appName)))
                return
        
        # Choosing time
        pubLocations = ravClient.get_application_publish_locations(self.appId)
        # Somewhat ironically, we only add cost-optimized option for admins
        if is_admin():
            pubLocations.insert(0, {'regionName': " ", 'cloudName': "auto-select cheapest"})
        
        if region == '@prompt':
            print(c.BOLD("\nAvailable publish locations:"))
            for i, loc in enumerate(pubLocations):
                print("  {})  {} {}".format(c.cyan(i), loc['cloudName'], loc['regionName']))
            
            # Prompt for provider selection
            selection = prompt_for_number(c.CYAN("\nSelect cloud provider/region in which to provision your VMs by entering a number: "), i)
        
            if 'auto-select cheapest' in pubLocations[selection]['cloudName']:
                optimizationLevel = 'COST_OPTIMIZED'
            else:
                optimizationLevel = 'PERFORMANCE_OPTIMIZED'
                preferredCloud = pubLocations[selection]['cloudName']
                preferredRegion = pubLocations[selection]['regionName']
        
        elif region == '@auto':
            optimizationLevel = 'COST_OPTIMIZED'
        
        else:
            for i, loc in enumerate(pubLocations):
                if region == loc['regionName']:
                    optimizationLevel = 'PERFORMANCE_OPTIMIZED'
                    preferredCloud = loc['cloudName']
                    preferredRegion = region
                    break
            else:
                print(c.RED("Invalid region specified!\n"))
                return
        
        # Build request dictionary
        req = {'preferredCloud' : preferredCloud, 'preferredRegion' : preferredRegion,
               'optimizationLevel': optimizationLevel, 'startAllVms': startAllVms}
        
        # Attempt publish request
        try:
            ravClient.publish_application(self.appId, req)
        except:
            print(c.red("\nProblem creating application!\n"))
            raise
        
        self.parent.numberOfPublishedApps += 1
        
        print(c.yellow("\nRavello now publishing your application (Could take 5 to 20 minutes)"))
        
        # Configure auto-stop (prompt if admin; otherwise set 1hr)
        if startAllVms:
            self.extend_app_autostop()
            self.loop_query_app_status(desiredState='STARTED')
        else:
            purge_app_cache(self.appId)
            print()
    
    
    def ui_command_start_app(self):
        """
        Start a stopped application.
        
        Attempts to start all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        if not is_admin():
            # Check that we don't have more started VMs than we should
            totalActiveVms = get_learner_active_vms(user)
            if totalActiveVms >= ravshOpt.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!\n"
                            .format(ravshOpt.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try this again")
                return
        # Start out by setting autostop
        self.extend_app_autostop()
        try:
            ravClient.start_application(self.appId)
        except:
            print(c.red("\nProblem starting application!\n"))
            raise
        print(c.yellow("\nApplication now starting"))
        purge_app_cache(self.appId)
        self.loop_query_app_status(desiredState='STARTED')
    
    
    def ui_command_stop_app(self):
        """
        Stop a running application.
        
        Sends a shutdown (via ACPI) to all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        try:
            ravClient.stop_application(self.appId)
        except:
            print("\nProblem stopping application!\n")
        print(c.yellow("\nApplication now stopping"))
        purge_app_cache(self.appId)
        self.loop_query_app_status(desiredState='STOPPED', intervalSec=15, totalMin=10)
    
    
    def ui_command_restart_app(self):
        """
        Restart a running application.
        
        Sends a reboot (via ACPI) to all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        try:
            ravClient.restart_application(self.appId)
        except:
            print("\nProblem restarting application!\n")
            raise
        print(c.yellow("\nApplication now restarting"))
        purge_app_cache(self.appId)
        self.loop_query_app_status(desiredState='STARTED')
    
    
    def generate_images(self):
        """Generate snapshot of all vms in the app. Not ready for primetime."""
        appDetails = get_app(self.appId)
        for i in range(len(appDetails['design']['vms'])):
            print("\n Generating snapshot for vm ",appDetails['design']['vms'][i]['name'])
            imageName = replace_bad_chars_with_underscores(appDetails['name'])
            imageName = appnamePrefix + imageName
            a = raw_input("\nEnter a name for your vm image [{}]: ".format(imageName))
            if a:
                imageName = replace_bad_chars_with_underscores(a)
            applicationId = appDetails['design']['vms'][i]['applicationId']
            vmId = appDetails['design']['vms'][i]['id']
            imageReq = {"applicationId": applicationId, "blueprint": "false", "vmId": vmId, "offline": "true", "imageName": imageName} 
            try:
                newImg = ravClient.create_images(imageReq)
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
        for vm in ravClient.get_vms(self.appId):
            Vm("%s" % vm['name'], self, vm['id'])
    
    def summary(self):
        app = get_app(self.appId)
        if app['published']:
            totalVms = len(app['deployment']['vms'])
            totalActiveVms = app['deployment']['totalActiveVms']
            totalErrorVms = app['deployment']['totalErrorVms']
            try:
                expirationTime = app['deployment']['expirationTime']
            except:
                expirationTime = None
                
            status = "{}/{} active".format(totalActiveVms, totalVms)
            
            if totalActiveVms > 0:
                hazHappy = True
                if expirationTime:
                    # Prepare expiration times
                    absoluteExpireTime = int(str(expirationTime)[:-3])
                    m, s = divmod(absoluteExpireTime - time(), 60)
                    absoluteExpireTime = datetime.fromtimestamp(absoluteExpireTime)
                    if m > 0:
                        status += ", auto-stop in {:.0f}:{:02.0f} min".format(m, s)
                    elif m == 0 and s > 0:
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
    
    
    def summary(self):
        app = get_app(self.appId)
        if app['published']:
            happyStates = ['STARTED', 'STARTING', 'RESTARTING', 'PUBLISHING' ]
            for vm in app['deployment']['vms']:
                if vm['id'] == self.vmId:
                    if vm['state'] in happyStates:
                        hazHappy = True
                    elif vm['state'] in 'STOPPED':
                        hazHappy = None
                    else:
                        hazHappy = False
                    return (vm['state'], hazHappy)
        else:
            return ("", None)
            
    
    def confirm_vm_is_state(self, state):
        for vm in ravClient.get_application(self.appId)['deployment']['vms']:
            if vm['id'] == self.vmId:
                if vm['state'] in state:
                    return True
                else:
                    print(c.red("\nVM is not {}!\n".format(state.lower())))
                    return False
        else:
            return False
    
    
    def print_vm_definition(self):
        """Pretty-print vm JSON in pager."""
        pager("JSON definition for VM '{}' in APPLICATION '{}'\n".format(self.vmName, self.appName) +
              prettify_json(ravClient.get_vm(self.appId, self.vmId)))
    
    
    def ui_command_print_vm_definition(self):
        """Pretty-print JSON for a VM."""
        print()
        self.print_vm_definition()
    
    
    def ui_command_start_vm(self):
        """
        Start a stopped VM.
        
        start_vm, stop_vm, & restart_vm all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STOPPED'):
            return
        self.parent.parent.extend_app_autostop()
        try:
            ravClient.start_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem starting VM!\n"))
            raise
        print(c.yellow("\nVM now starting\n"))
        purge_app_cache(self.appId)
    
    
    def ui_command_reset_vm_to_last_shutdown_state(self):
        """
        Reset VM to the state it was in as of last shutdown.
        
        Every VM has its disk state automatically snapshotted at shutdown.
        This command re-publishes the VM using the last snapshot state (which is
        not necessarily the best working state).
        
        To reset a VM to a pristine state (i.e., the state of the VM when the
        app was originally created), you must first ensure the VM never shuts
        down ... or make sure you run this command before any shutdown.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        try:
            ravClient.redeploy_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem resetting VM!\n"))
            raise
        print(c.yellow("\nVM was destroyed and is being re-published from state of last full shutdown"))
        print("FQDN should stay the same; VNC URL will change; ssh host key might change\n")
        purge_app_cache(self.appId)
    
    
    def ui_command_stop_vm(self):
        """
        Gracefully stop a running VM.
        
        start_vm, stop_vm, & restart_vm all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STARTED'):
            return
        try:
            ravClient.stop_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem stopping VM!\n"))
            raise
        print(c.yellow("\nVM now stopping\n"))
        purge_app_cache(self.appId)
    
    
    def ui_command_poweroff_vm(self):
        """
        Cut the power to a VM, hopefully forcing it off immediately.
        
        Sadly, this does not always work.
        In particularl, Ravello has a bug where VMs in 'STOPPING' state don't
        respond to this.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        #~ if not self.confirm_vm_is_state('STARTED'):
            #~ return
        try:
            ravClient.poweroff_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem powering off VM!\n"))
            raise
        print(c.yellow("\nVM should be immediately forced off\n"))
        purge_app_cache(self.appId)
    
    
    def ui_command_restart_vm(self):
        """
        Gracefully restart a running VM.
        
        start_vm, stop_vm, & restart_vm all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STARTED'):
            return
        try:
            ravClient.restart_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem restarting VM!\n"))
            raise
        print(c.yellow("\nVM now restarting\n"))
        purge_app_cache(self.appId)
