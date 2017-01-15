# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from sys import stdout, stdin
from pydoc import pager, pipepager
from time import sleep, time
from stat import S_ISDIR, S_ISREG
from os import path, makedirs, chmod, remove, stat
from glob import glob
from datetime import datetime, date
from calendar import month_name
from operator import itemgetter
import json
import subprocess
import termios
import re

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
import string_ops
import ui_methods as ui
try:
    import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/blob/ravshello-stable/lib/ravello_sdk.py\n")
    raise

# Globals
user = c = rOpt = rClient = rCache = appnamePrefix = None
defaultAppExpireTime = 120
defaultAppExtendTime = 60
maxLearnerExtendTime = 120


def is_admin():
    if rOpt.enableAdminFuncs:
        return True
    else:
        return False


def complete_path(path, stat_fn):
    """Return filenames to ui_complete_*() meths for path completion.
    
    Taken from targetcli's ui_backstore module.
    """
    filtered = []
    for entry in glob(path + '*'):
        st = stat(entry)
        if S_ISDIR(st.st_mode):
            filtered.append(entry + '/')
        elif stat_fn(st.st_mode):
            filtered.append(entry)
    # Put directories at the end
    return sorted(filtered,
                  key=lambda s: '~'+s if s.endswith('/') else s)


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


def main(opt, client):
    # Set some important globals
    global rOpt, rClient, user, appnamePrefix, c, rCache
    rOpt = opt
    rClient = client
    user = rOpt.user
    appnamePrefix = 'k:{}__'.format(user)
    c = rOpt.c
    rCache = ui.RavelloCache(rClient)
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
    if not rOpt.enableColor:
        shell.prefs['color_mode'] = False
    if not rOpt.showAllApps:
        # Turn off max depth restriction for admins in restricted-view mode
        shell.prefs['tree_max_depth'] = 0
    c.verbose("  Fetching data from Ravello . . . ", end='')
    stdout.flush()
    # Start configshell
    try:
        root_node = RavelloRoot(shell)
    except:
        print(c.RED("\n  UNHANDLED EXCEPTION getting data from Ravello\n"))
        print("If problem persists, send this message with below traceback to rsaw@redhat.com")
        raise
    c.verbose("Done!\n")
    # For some reason sleep is necessary here to fix issue #49
    sleep(0.1)
    if is_admin() and rOpt.cmdlineArgs:
        # Run args non-interactively
        if rOpt.scriptFile:
            print(c.yellow("Ignoring script file because cmdline args present\n"))
        shell.run_cmdline(rOpt.cmdlineArgs)
    elif is_admin() and rOpt.scriptFile:
        # Run script file non-interactively
        try:
            shell.run_script(rOpt.scriptFile)
        except:
            print(c.red("Unable to open script file\n"))
    elif is_admin():
        shell.run_interactive(exit_on_error=rOpt.enableDebugging)
    else:
        # What to do when not admin
        if rOpt.cmdlineArgs or rOpt.scriptFile:
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
        print(" │ COMMANDS: Use tab-completion to see commands specific to each directory")
        print(" │ GET HELP: Use `{}`".format(c.BOLD('help')))
        print(" │")
        print(" │ Your first time?")
        print(" │   - First: use `{}` command".format(c.BOLD('cd apps')))
        print(" │   - Next: press TAB-TAB to see available commands")
        print(" │   - Next: use `{}` TAB-TAB command to get started".format(c.BOLD('new')))
        print(" │   - Optional: `{}` into new app directory and press TAB-TAB to see commands".format(c.BOLD('cd')))
        print(" │   - Optional: use `{}` command to add an hour to the timer".format(c.BOLD('extend_autostop')))
        print(" └──────────────────────────────────────────────────────────────────────────────\n")
        shell.run_interactive(exit_on_error=rOpt.enableDebugging)


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
            status = "Local admin user: {}, Ravello user: {}".format(
                user, rClient._username)
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
            return ("To populate, run: refresh", False)
        
    def refresh(self):
        self._children = set([])
        rCache.update_user_cache()
        self.numberOfEvents = 0
        for eventName in rClient.get_events():
            Event("%s" % eventName.swapcase(), self)
            self.numberOfEvents += 1
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
    
    def ui_command_print_event_names(self, outputFile='@pager'):
        """
        Pretty-print JSON list of Ravello event names.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system; otherwise output will be piped to pager.
        
        Alerts can be registered for any of the returned event names with the
        register command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_event_names()
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.get_events(), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing event names\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Exported event names to file: '{}'\n".format(outputFile)))
    
    def ui_complete_print_event_names(self, parameters, text, current_param):
        if current_param != 'outputFile':
            return []
        completions = complete_path(text, S_ISREG)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions
    
    def print_registered_alerts(self):
        pager("JSON list of REGISTERED USER ALERTS\n" +
              ui.prettify_json(rClient.get_alerts()))
    
    def ui_command_print_registered_alerts(self, outputFile='@pager'):
        """
        Pretty-print JSON list of userAlerts registered.
        
        Assuming the current Ravello user is an admin, they will actually see
        all alerts in the organization.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system.
        
        Create alerts with the register command.
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_registered_alerts()
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.get_alerts(), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing userAlerts\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Exported userAlerts to file: '{}'\n".format(outputFile)))
    
    def ui_complete_print_registered_alerts(self, parameters, text, current_param):
        if current_param != 'outputFile':
            return []
        completions = complete_path(text, S_ISREG)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions


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
        eventAlerts = rCache.get_alerts_for_event(self.eventName)
        if eventAlerts:
            for a in eventAlerts:
                UserAlert(
                    c.replace_bad_chars_with_underscores(rCache.userCache[a['userId']]['email']),
                    self, a['alertId'], a['userId'])
    
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
    
    Path: /events/{EVENT_NAME}/{USER_IDENTIFIER}/
    """
    
    def __init__(self, userString, parent, alertId, userId):
        ConfigNode.__init__(self, userString, parent)
        self.userId = userId
        self.alertId = alertId
    
    #~ def summary(self):
        #~ return (get_user(self.userId)['email'], None)
    
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
            outputFile='@pager'):
        """
        Pretty-print JSON list of notification search results.
        
        Optionally specify outputFile as a relative or absolute path on the
        local system; otherwise output is piped to pager.
        
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
                  ui.prettify_json(rClient.search_notifications(req)))
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.search_notifications(req), f, indent=4)
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
                else:
                    j = month_name[month]
            except:
                print(c.RED("Invalid month specification!\n"))
                raise
        return month, year
    
    def ui_command_inspect_all_charges(self, month='@prompt',
            year=date.today().year, outputFile='@pager'):
        """
        Print full JSON for all charges in a specific month.
        
        Optionally specify *month* to avoid being prompted.
        Setting *month* to 0 is the same as specifying the number of the current
        month. Specifying a negative number for *month* will cause *year*
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The *year* can only be specified as an absolute (positive) number.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system.
        """
        print()
        month = self.ui_eval_param(month, 'string', '@prompt')
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        year = self.ui_eval_param(year, 'number', date.today().year)
        try:
            month, year = self.validate_or_prompt_for_month(month, year)
        except:
            return
            
        print(c.yellow("Pulling summary of charges for {}-{} . . .\n"
                       .format(year, month_name[month])))
        try:
            b = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        
        if outputFile == '@pager':
            pager("Full details of charges incurred for all apps since beginning of the month\n" +
                  ui.prettify_json(b))
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
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
    
    def _complete_file_month_year(self, parameters, text, current_param):
        if current_param == 'outputFile':
            completions = complete_path(text, S_ISREG)
            if len(completions) == 1 and not completions[0].endswith('/'):
                completions = [completions[0] + ' ']
            return completions
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
            year=date.today().year, sortBy='nick', outputFile='@term'):
        """
        Export per-app details of a particular month in CSV format.
        
        Optionally specify *month* to avoid being prompted.
        Setting *month* to 0 is the same as specifying the number of the
        current month. Specifying a negative number for *month* will cause year
        specification to be ignored (-1 is last month, -24 is 2 years ago).
        
        The *year* can only be specified as an absolute (positive) number.

        With *sortBy*, charges can be sorted by Ravello user login ('user') or
        ravshello nickname ('nick').
        
        Optionally specify *outputFile* as @pager or as a relative / absolute
        path on the local system.
        """
        
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@term')
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
        print(c.yellow("Pulling summary of charges for {}-{} . . .\n"
                       .format(year, month_name[month])))
        try:
            b = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        csv = self.gen_csv(b, sortBy)
        if outputFile == '@term':
            print(csv)
        elif outputFile == '@pager':
            pager(csv)
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    f.write(csv)
            except IOError as e:
                print(c.RED("Problem writing billing information!\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Wrote billing information as CSV to file: '{}'".format(outputFile)))
        print()
    
    def ui_complete_export_month_to_csv(self, parameters, text, current_param):
        return self._complete_file_month_year_sortby(parameters, text, current_param)
    
    def ui_command_this_months_summary(self, sortBy='nick', outputFile='@pager'):
        """
        Print billing summary of all charges since beginning of this month.
        
        With *sortBy*, charges can be sorted by Ravello user login ('user') or
        ravshello nickname ('nick').
        
        Optionally specify *outputFile* as @term or as a relative / absolute
        path on the local system.
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
            b = rClient.get_billing()
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        txt = self.gen_txt_summary(b, sortBy)
        if outputFile == '@term':
            print(txt)
        elif outputFile == '@pager':
            pipepager(txt, cmd='less -R')
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    f.write(txt)
            except IOError as e:
                print(c.RED("Problem writing billing information!\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Wrote billing information to file: '{}'\n".format(outputFile)))
    
    def ui_complete_this_months_summary(self, parameters, text, current_param):
        if current_param == 'outputFile':
            completions = complete_path(text, S_ISREG)
            if len(completions) == 1 and not completions[0].endswith('/'):
                completions = [completions[0] + ' ']
            return completions
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
        
        Optionally specify *outputFile* as @term or as a relative / absolute
        path on the local system.
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
        print(c.yellow("Pulling summary of charges for {}-{} . . .\n"
                       .format(year, month_name[month])))
        try:
            b = rClient.get_billing_for_month(year, month)
        except:
            print(c.red("Problem getting billing info!\n"))
            raise
        txt = self.gen_txt_summary(b, sortBy)
        if outputFile == '@term':
            print(txt)
        elif outputFile == '@pager':
            pipepager(txt, cmd='less -R')
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    f.write(txt)
            except IOError as e:
                print(c.RED("Problem writing billing information!\n"
                            "  {}\n".format(e)))
                return
            print(c.green("Wrote billing information to file: '{}'\n".format(outputFile)))
    
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
                upTime = "UNDEFINED"
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
            totalCharges = 0
            hours = 0
            for product in app['charges']:
                try:
                    m = re.search('hour', product['unitName'], re.IGNORECASE)
                    if m:
                        hours += product['productCount']
                except:
                    pass
                try:
                    totalCharges += product['summaryPrice']
                except:
                    pass
                prodName = product['productName'].replace('Performance Opt', 'Perf-Opt').replace('Cost Opt', 'Cost-Opt')
                if prodName not in chargesByProduct:
                    chargesByProduct[prodName] = {
                        'summaryPrice': 0,
                        'productRate': product['productRate'],
                        'unitName': product['unitName'],
                        }
                chargesByProduct[prodName]['summaryPrice'] += product['summaryPrice']
            try:
                creationTime = int(str(app['creationTime'])[:-3])
            except:
                creationTime = 0
            appsByUser[user].append({
                'appName': appName,
                'unitHours': hours,
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
            userTotalHours = 0
            userGrandTotal = 0
            out.append(c.BLUE("{}:".format(user)))
            out.append(c.magenta("    Charges\tHours\tCreation Time\tApplication Name"))
            for app in sorted(appsByUser[user], key=itemgetter('creationTime')):
                tc = app['totalCharges']
                userGrandTotal += tc
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
                userTotalHours += app['appHours']
                if not app['appHours']:
                    hours = "N/A"
                else:
                    hours = "{:g}".format(app['appHours'])
                out.append("    {}\t{}\t{}\t{}"
                           .format(tc, hours, creationTime, app['appName']))
            acctGrandTotal += userGrandTotal
            if not app['totalCharges'] == userGrandTotal:
                out.append("    -----------------")
                out.append("    " +
                           c.REVERSE("${:8.2f}\t{:g}"
                                     .format(userGrandTotal, userTotalHours)))
            out.append("")
        prodGrandTotal = 0
        out.append("")
        out.append(c.BLUE("Charges by product:"))
        out.append(c.magenta("    Charges\tUnit Price\tCount\tProduct Name"))
        for product in sorted(chargesByProduct):
            tc = chargesByProduct[product]['summaryPrice']
            prodGrandTotal += tc
            if tc < 15:
                tc = c.green("${:8.2f}".format(tc))
            elif tc < 50:
                tc = c.yellow("${:8.2f}".format(tc))
            elif tc < 90:
                tc = c.YELLOW("${:8.2f}".format(tc))
            elif tc < 130:
                tc = c.red("${:8.2f}".format(tc))
            else:
                tc = c.RED("${:8.2f}".format(tc))
            out.append(
                "    {}\t${:.2f} {}\t{:5.1f}\t{}"
                .format(
                    tc,
                    chargesByProduct[product]['productRate'],
                    chargesByProduct[product]['unitName'].replace('Hour', 'Hr'),
                    chargesByProduct[product]['summaryPrice'] / chargesByProduct[product]['productRate'],
                    product))
        out.append("    --------")
        out.append(
            "    "  +
            c.REVERSE("${:8.2f}\tMonthly charges grand total".format(prodGrandTotal)))
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
        rCache.update_user_cache()
        for userId in rCache.userCache:
            if not userId == '_timestamp':
                User(c.replace_bad_chars_with_underscores(rCache.userCache[userId]['email']),
                    self, userId)
                self.numberOfUsers += 1
                if 'ADMIN' in rCache.userCache[userId]['roles']:
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
        user = rCache.get_user(self.userId)
        if 'ADMIN' in user['roles']:
            r = True
        else:
            r = None
        return (user['email'], r)
    
    def ui_command_get_info(self):
        """
        Pretty-print user details.
        """
        print()
        print(ui.prettify_json(rCache.get_user(self.userId)))
        print()
    
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
            return ("{} blueprints".format(self.numberOfBps), None)
        else:
            return ("To populate, run: refresh", False)
    
    def refresh(self):
        self._children = set([])
        self.numberOfBps = 0
        for bp in rClient.get_blueprints():
            Bp("%s" % bp['name'], self, bp['id'], bp['creationTime'])
            self.numberOfBps += 1
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
    
    def ui_command_backup_all(self, bpDir='@home'):
        """
        Export each & every blueprint to a JSON file.
        
        Optionally specify an absolute or relative path; otherwise, default
        *bpDir* of @home maps to <CFGDIR>/blueprints. Note also that <CFGDIR>
        defaults to '~/.ravshello/', but can be tweaked with the cmdline option
        '--cfgdir'.
        
        File names are determined automatically from the blueprint name (plus an
        extension of ".json"). Existing files are overwritten.
        """
        print()
        bpDir = self.ui_eval_param(bpDir, 'string', '@home')
        if bpDir == '@home':
            bpDir = path.join(rOpt.userCfgDir, 'blueprints')
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
        for bp in rClient.get_blueprints():
            f = path.join(bpDir, bp['name'] + '.json')
            try:
                with open(f, 'w') as outfile:
                    json.dump(rClient.get_blueprint(bp['id']), outfile, indent=4)
            except IOError as e:
                print(c.red("Problem exporting bp '{}'\n  {}".format(bp['name'], e)))
                continue
            print(c.green("Exported bp to file: '{}'".format(f)))
        print()
    
    def ui_complete_backup_all(self, parameters, text, current_param):
        if current_param != 'bpDir':
            return []
        completions = complete_path(text, S_ISDIR)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions
    
    def create_bp_from_json_obj(self, bpDefinition, bpFileName=None, name='@prompt', desc='@prompt'):
        """Create a new blueprint from a json blueprint defition."""
        def _delete_temporary_app(appId, appName):
            try:
                rClient.delete_application(newApp['id'])
            except:
                print("\nNotice: Unable to delete temporary unpublished application '{}'\n"
                      .format(appName))
        
        # Set default bp name from bp json or filename
        # Set default description different depending on whether bp created from file or existing bp
        if not bpFileName:
            # Generate a new blueprint name suggestion based off current one
            bpName = ravello_sdk.new_name(rClient.get_blueprints(), bpDefinition['name'] + '_')
            bpDescription = "Created by {} as a copy of blueprint '{}'".format(user, bpDefinition['name'])
        else:
            bpName = path.basename(bpFileName)
            bpDescription = "Created by {} from blueprint file '{}'".format(user, bpName)
            bpName = bpName.rstrip('.json')
        
        # Prompt for a blueprint name if necessary
        if name == '@prompt':
            b = raw_input(c.CYAN("\nEnter a unique name for your new blueprint [{}]: ".format(bpName)))
            if len(b): bpName = b
        elif name == '@auto':
            pass
        else:
            bpName = name
        
        # Create temporary application from bp
        appName = appnamePrefix + 'BpTempApp'
        appName = ravello_sdk.new_name(rClient.get_applications(), appName + '_')
        appDescription = "Temporary app used to restore blueprint from file"
        appDesign = bpDefinition['design']
        appReq = {'name' : appName, 'description' : appDescription, 'design': appDesign}
        try:
            newApp = rClient.create_application(appReq)
        except:
            print(c.red("\nUnable to create temporary application '{}'! "
                        "Cannot continue with restore!\n".format(appName)))
            raise
        
        # Prompt for description if necessary
        if desc == '@prompt':
            d = raw_input(c.CYAN("\nOptionally enter a description for your new blueprint [{}]: ".format(bpDescription)))
            if len(d): bpDescription = d
        elif desc == '@auto':
            pass
        else:
            bpDescription = desc
        
        # Create request dictionary and post new bp
        req = {"applicationId": newApp['id'], "blueprintName": bpName, "offline": "true", "description": bpDescription}
        try:
            newBp = rClient.create_blueprint(req)
        except:
            print(c.red("\nProblem creating new blueprint!\n"))
            _delete_temporary_app(newApp['id'], appName)
            raise
        print(c.green("\nSUCCESS! New blueprint '{}' created!".format(bpName)))
        
        # Delete temp app
        _delete_temporary_app(newApp['id'], appName)
        # Add new bp to directory tree
        Bp("%s" % newBp['name'], self, newBp['id'], newBp['creationTime'])
        print()
    
    def ui_command_import_from_file(self, inputFile='@prompt',
            name='@prompt', desc='@prompt'):
        """
        Create a blurprint from JSON file in <CFGDIR>/blueprints.
        
        By specifying *inputFile* on the command-line, you can use a full path,
        i.e., choices are not restricted to <CFGDIR>/blueprints. Note also that
        <CFGDIR> defaults to '~/.ravshello/', but can be tweaked with the
        cmdline option '--cfgdir'.
        
        This command is only useful after running one of the following:
            - backup_all
            - backup
            - print_def outputFile=PATH
        
        Optionally specify *name* and/or *desc* on the command-line to avoid
        prompting (both default to '@prompt' and both can be set to '@auto'
        to skip prompting).
        """
        inputFile = self.ui_eval_param(inputFile, 'string', '@prompt')
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        if inputFile == '@prompt':
            print()
            # Get a list of what is in local cache
            c1 = subprocess.Popen(['ls', path.join(rOpt.userCfgDir, 'blueprints')],
                                  stdout=subprocess.PIPE)
            bpFileList = c1.communicate()[0].strip('\n').split('\n')
            bpFileList = filter(None, bpFileList)
            if not len(bpFileList):
                print(c.red("There are not any blueprint files in your local cache ({})!\n"
                            .format(path.join(rOpt.userCfgDir, 'blueprints'))))
                print("(They would need to have been created by the `{}`, `{}`, or `{}` commands)\n"
                      .format(c.BOLD('backup_all'), c.BOLD('backup'), c.BOLD('print_def')))
                return
            # Enumerate through list of files
            print(c.BOLD("Blueprint json definitions available in {}:"
                       .format(path.join(rOpt.userCfgDir, 'blueprints'))))
            for i, bp in enumerate(bpFileList):
                print("  {})  {}".format(c.cyan(i), bp))
            # Prompt for bp selection
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter the number of a file you wish to create a new blueprint from: "),
                endRange=i)
            inputFile = path.join(rOpt.userCfgDir, 'blueprints', bpFileList[selection])
        # Load chosen blueprint def file into json obj
        try:
            with open(inputFile) as f:
                bpDefinition = json.load(f)
        except:
            print(c.RED("Problem importing json data from file!\n"))
            raise
        # Make the magic happen
        self.create_bp_from_json_obj(bpDefinition, inputFile, name, desc)
    
    def ui_complete_import_from_file(self, parameters, text, current_param):
        if current_param == 'inputFile':
            completions = complete_path(text, S_ISREG)
            if len(completions) == 1 and not completions[0].endswith('/'):
                completions = [completions[0] + ' ']
            return completions
        elif current_param == 'name':
            L = ['@prompt', '@auto']
            for bp in rClient.get_blueprints():
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
    
    def delete(self):
        try:
            rClient.delete_blueprint(self.bpId)
        except:
            print(c.red("Problem deleting blueprint!\n"))
            raise
        print(c.green("Deleted blueprint {}\n".format(self.bpName)))
        self.parent.remove_child(self)
    
    def ui_command_delete(self, noconfirm='false', nobackup='false'):
        """
        Delete a blueprint.
        
        By default, confirmation will be required to delete the blueprint.
        Disable prompt with noconfirm=true.
        
        By default, blueprint will automatically be saved to
        <CFGDIR>/blueprints/<BlueprintName>.json, overwriting any existing
        file. Disable with nobackup=true.
        """
        noconfirm = self.ui_eval_param(noconfirm, 'bool', False)
        nobackup = self.ui_eval_param(nobackup, 'bool', False)
        print()
        if not noconfirm:
            c.slow_print(c.RED("Deleting a blueprint cannot be undone -- make sure you know what you're doing\n"))
            response = raw_input(c.CYAN("Continue with blueprint deletion? [y/N] "))
            print()
        if noconfirm or response == 'y':
            if not nobackup:
                print("Backing up blueprint definition to local file before deleting . . .")
                self.ui_command_backup()
                print("Blueprint can be recreated from file later with {} command\n"
                      .format(c.BOLD("import_from_file")))
            self.delete()
        else:
            print("Leaving bp intact (probably a good choice)\n")
    
    def ui_complete_delete(self, parameters, text, current_param):
        if current_param in ['noconfirm', 'nobackup']:
            completions = [a for a in ['false', 'true']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_find_pub_locations(self):
        """
        Print details about available publish locations for a blueprint.
        """
        print()
        pager("Blueprint available publish locations for '{}'\n".format(self.bpName) +
              ui.prettify_json(rClient.get_blueprint_publish_locations(self.bpId)))
    
    def print_def(self):
        pager("JSON definition for BLUEPRINT '{}'\n".format(self.bpName) +
              ui.prettify_json(rClient.get_blueprint(self.bpId)))
    
    def ui_command_print_def(self, outputFile='@pager'):
        """
        Pretty-print blueprint JSON in pager or export to outputFile.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system (tab-completion available).
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_def()
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.get_blueprint(self.bpId), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing bp definition for '{}'\n"
                            "{}\n".format(self.bpName, e)))
                return
            print(c.green("Exported bp definition to file: '{}'\n".format(outputFile)))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param != 'outputFile':
            return []
        completions = complete_path(text, S_ISREG)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions
    
    def ui_command_backup(self):
        """
        Export blueprint definition to a JSON file in <CFGDIR>/blueprints.
        
        File names are determined automatically from the blueprint name (plus an
        extension of ".json"). Existing files are overwritten.
        
        To save to a specific path, use print_def command.
        """
        print()
        d = path.join(rOpt.userCfgDir, 'blueprints')
        if not path.exists(d):
            makedirs(d, 0775)
        f = path.join(d, self.bpName + '.json')
        try:
            with open(f, 'w') as outfile:
                json.dump(rClient.get_blueprint(self.bpId), outfile, indent=4)
        except:
            print(c.red("Problem exporting bp '{}'".format(self.bpName)))
            raise
        print(c.green("Exported bp to file: '{}'\n".format(f)))
    
    def ui_command_copy(self, name='@prompt', desc='@prompt'):
        """
        Create a copy of an existing blueprint.
        
        Optionally specify *name* and/or *desc* on the command-line to avoid
        prompting (both default to '@prompt' and both can be set to '@auto'
        to skip prompting).
        """
        name = self.ui_eval_param(name, 'string', '@prompt')
        desc = self.ui_eval_param(desc, 'string', '@prompt')
        # Get current blueprint def
        bpDefinition = rClient.get_blueprint(self.bpId)
        # Make the magic happen
        self.parent.create_bp_from_json_obj(bpDefinition, name=name, desc=desc)
    
    def ui_complete_copy(self, parameters, text, current_param):
        if current_param == 'name':
            L = ['@prompt', '@auto']
            for bp in rClient.get_blueprints():
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
                        print(c.yellow("\nThere is a new application available to you since you started ravshello!"))
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
            startAllVms='true'):
        """
        Interactively create a new application from a base blueprint.
        
        Optionally specify all parameters on the command-line.
        Note that application *name*, *desc*, *region* can be set to '@auto';
        however, due to a limitation in ConfigShell, *desc* cannot accept
        multiple arguments (i.e., you cannot pass multiple words with spaces,
        even if you use quotes).
        
        If run with publish=false, the publish command can be run
        later from the app-specific context (/apps/APPNAME/).
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
        blueprints = rClient.get_blueprints()
        for bp in blueprints:
            try:
                description = bp['description']
            except:
                description = ''
            if is_admin() or any(tag in description for tag in rOpt.learnerBlueprintTag) or '#k:{}'.format(user) in description:
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
            selection = ui.prompt_for_number(
                c.CYAN("\nEnter number of blueprint: "), endRange=i)
            baseBlueprintName = allowedBlueprints[selection]
        else:
            baseBlueprintName = blueprint
            
        # Quit if invalid blueprint name
        if baseBlueprintName not in allowedBlueprints or not ui.iterate_json_keys_for_value(blueprints, 'name', baseBlueprintName):
            print(c.RED("\nInvalid blueprint name!\n"))
            return
        
        # Convert blueprint name to id
        for bp in blueprints:
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
                        print(c.red(
                            "\nNote that configshell (which ravshello uses) won't accept certain chars in paths\n"
                            "Namely, only the following are allowed: A-Za-z0-9:_.-\n"
                            "In order handle apps with characters BESIDES those, one would have to use the\n"
                            "*interactive* cd command with arrow keys"))
                        response = raw_input(c.CYAN("\nReplace bad characters with underscores? [y/N] "))
                        if response == 'y':
                            a = aFixed
                    appName = a
        else:
            appName = name
            
        appName = appnamePrefix + appName
        
        # Ensure there's not already an app with that name
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
        
        appDesc += "[Created w/ravshello {} by {}]".format(rOpt.ravshelloVersion.split()[1], user)
        
        # Build request dictionary
        req = {'name' : appName, 'description' : appDesc, 'baseBlueprintId': baseBlueprintId}
        
        # Attempt create request!
        try:
            newApp = rClient.create_application(req)
        except:
            print(c.red("\nProblem creating application!\n"))
            raise
        
        self.numberOfApps += 1
        
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
            blueprints = rClient.get_blueprints()
            for bp in blueprints:
                try:
                    description = bp['description']
                except:
                    description = ''
                if is_admin() or any(tag in description for tag in rOpt.learnerBlueprintTag) or '#k:{}'.format(user) in description:
                    allowedBlueprints.append(bp['name'])
            completions = [a for a in allowedBlueprints
                           if a.startswith(text)]
        elif current_param in ['name', 'desc']:
            completions = [a for a in ['@prompt', '@auto']
                           if a.startswith(text)]
        elif current_param == 'publish':
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
                blueprints = rClient.get_blueprints()
                for bp in blueprints:
                    try:
                        description = bp['description']
                    except:
                        description = ''
                    if is_admin() or any(tag in description for tag in rOpt.learnerBlueprintTag) or '#k:{}'.format(user) in description:
                        allowedBlueprints[bp['name']] = bp['id']
                try:
                    bpid = allowedBlueprints[blueprint]
                except:
                    completions = [a for a in L
                                   if a.startswith(text)]
                else:
                    pubLocations = rClient.get_blueprint_publish_locations(bpid)
                    for p in pubLocations:
                        L.append(p['regionName'])
                    completions = [a for a in L
                                   if a.startswith(text)]
        elif current_param == 'startAllVms':
            completions = [a for a in ['true', 'false']
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
    
    def __init__(self, name, parent, appId):
        ConfigNode.__init__(self, name, parent)
        self.appId = appId
        self.appName = name
        Vms(self)
    
    def summary(self):
        app = rCache.get_app(self.appId)
        if app['published']:
            region = app['deployment']['cloudRegion']['name']
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
            try:
                currentDescription = app['description']
                m = re.search('_{(.*)}_', currentDescription)
                if m:
                    note = "; {}".format(m.group(1))
                else:
                    note = ""
            except:
                note = ""
            return ("{} in {}{}".format(appState, region, note), hazHappy)
        else:
            return ("Unpublished draft", None)
    
    def print_message_app_not_published(self):
        print(c.red("Application has not been published yet!\n"))
        print("To publish application, run command:")
        print(c.BOLD("    /apps/{}/ publish\n".format(self.appName)))
    
    def confirm_app_is_published(self):
        rCache.update_app_cache(self.appId)
        if not rCache.get_app(self.appId)['published']:
            self.print_message_app_not_published()
            return False
        return True
    
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
            if totalMin > maxLearnerExtendTime:
                print(c.red("\nUsing maximum learner watch-time of {} min"
                            .format(maxLearnerExtendTime)))
                totalMin = maxLearnerExtendTime
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
        vmDetails, regionName, expirationTime = rCache.get_application_details(self.appId)
        if not vmDetails:
            self.print_message_app_not_published()
            return None, None
        # Defaults
        allVmsAreStarted = True
        allVmsAreStopped = True
        sshKey = ""
        if rOpt.cfgFile['sshKeyFile']:
            sshKey = " -i {}".format(rOpt.cfgFile['sshKeyFile'])
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
        # Print
        print(
            c.BOLD("App VMs in region {} ".format(regionName)) +
            autoStopMessage)
        print()
        for vm in vmDetails:
            ssh = vnc = None
            # Set ssh command
            if vm['ssh']['fqdn']:
                ssh = c.cyan("ssh{}{} root@{}".format(sshKey, vm['ssh']['port'], vm['ssh']['fqdn']))
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
                if vm['nics']:
                    for i in vm['nics']:
                        print("     NIC {}".format(i['name']))
                        print("       Private IP:       {}".format(i['ip_Private']))
                        for ip in i['ip_Additional']:
                            print("       Private IP:       {}".format(ip))
                        if i['ip_Elastic']:
                            print("       Public Elastic:   {} ({})".format(i['ip_Elastic'], i['fqdn']))
                        if i['ip_Public']:
                            print("       Public Static:    {} ({})".format(i['ip_Public'], i['fqdn']))
                        if i['ip_Forwarder'] and i['services']:
                            print("       Public DNAT:      {} ({})".format(i['ip_Forwarder'], i['fqdn']))
                        for s in i['services']:
                            print("       External Svc:     {svc} {export}/{proto} maps to internal {inport}/{proto}".format(
                                svc=s['name'], export=s['externalPort'], proto=s['protocol'], inport=s['portRange']))
                if vm['state'] not in 'STARTING':
                    if ssh:
                        print("     SSH Command:        {}".format(ssh))
                    if vnc:
                        print("     VNC Web URL:        {}".format(vnc))
            print()
        return allVmsAreStarted, allVmsAreStopped
    
    def extend_autostop(self, minutes=60):
        if not self.confirm_app_is_published():
            return False
        req = {'expirationFromNowSeconds': minutes * 60}
        try:
            rClient.set_application_expiration(self.appId, req)
        except:
            print(c.red("\nProblem setting application auto-stop!"))
            return
        print(c.green("\nApp auto-stop set for {} minutes from now"
                      .format(minutes)))
        rCache.purge_app_cache(self.appId)
    
    def ui_command_extend_autostop(self, minutes=defaultAppExtendTime):
        """
        Set the application auto-stop time via *minutes*.
        
        Defaults to 60 min (defaultAppExtendTime). Learners can set the
        auto-stop timer from 0 to 120 min (maxLearnerExtendTime).
        Admins can set any value, including '-1' which disables auto-stop timer.
        """
        minutes = self.ui_eval_param(minutes, 'number', defaultAppExtendTime)
        if not is_admin():
            if minutes > maxLearnerExtendTime:
                print(c.red("\nUsing maximum learner auto-stop time of {} minutes"
                            .format(maxLearnerExtendTime)))
                minutes = maxLearnerExtendTime
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
    
    def print_def(self):
        pager("JSON definition for APPLICATION '{}'\n".format(self.appName) +
              ui.prettify_json(rClient.get_application(self.appId)))
    
    def ui_command_print_def(self, outputFile='@pager'):
        """
        Pretty-print app JSON in pager or export to *outputFile*.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system (tab-completion available).
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_def()
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.get_application(self.appId), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing app definition for '{}'\n"
                            "  {}\n".format(self.appName, e)))
                return
            print(c.green("Exported app definition to file: '{}'\n".format(outputFile)))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param != 'outputFile':
            return []
        completions = complete_path(text, S_ISREG)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions
    
    def delete_app(self):
        if rCache.get_app(self.appId)['published']:
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
    
    def ui_command_publish(self, region='@prompt', startAllVms='true'):
        """
        Interactively publish an application to the cloud.
        
        Optionally specify *region* and whether all VMs should be started after
        publishing (*startAllVms*).
        """
        region = self.ui_eval_param(region, 'string', '@prompt')
        startAllVms = self.ui_eval_param(startAllVms, 'bool', True)
        # Sanity check
        if rCache.get_app(self.appId)['published'] is True:
            print(c.red("\nApplication already published!\n"))
            return
        # Set defaults
        selection = preferredRegion = None
        if not is_admin():
            # Check that we don't have more published apps than we should
            totalActiveVms = get_num_learner_active_vms(user)
            if self.parent.numberOfPublishedApps >= rOpt.maxLearnerPublishedApps:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of published apps!"
                            .format(rOpt.maxLearnerPublishedApps)))
                print("Delete an app and try running command:")
                print(c.BOLD("    /apps/{}/ publish\n".format(self.appName)))
                return
            elif totalActiveVms >= rOpt.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!"
                            .format(rOpt.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try running command:")
                print(c.BOLD("    /apps/{}/ start\n".format(self.appName)))
                return
        # Choosing time
        pubLocations = rClient.get_application_publish_locations(self.appId)
        # Somewhat ironically, we only add cost-optimized option for admins
        if is_admin():
            pubLocations.insert(0, {'regionName': "@auto", 'regionDisplayName': "auto-select cheapest"})
        if region == '@prompt':
            print(c.BOLD("\nAvailable publish locations:"))
            for i, loc in enumerate(pubLocations):
                print("  {})  {}".format(c.cyan(i), loc['regionName']))
            # Prompt for provider selection
            selection = ui.prompt_for_number(
                c.CYAN("\nSelect cloud region in which to provision your VMs by entering a number: "),
                endRange=i)
            if '@auto' in pubLocations[selection]['regionName']:
                optimizationLevel = 'COST_OPTIMIZED'
            else:
                optimizationLevel = 'PERFORMANCE_OPTIMIZED'
                preferredRegion = pubLocations[selection]['regionName']
        elif region == '@auto':
            optimizationLevel = 'COST_OPTIMIZED'
        else:
            for i, loc in enumerate(pubLocations):
                if region == loc['regionName']:
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
            self.extend_autostop(minutes=defaultAppExpireTime)
            self.loop_query_status(desiredState='STARTED')
        else:
            rCache.purge_app_cache(self.appId)
            print()
    
    def ui_complete_publish(self, parameters, text, current_param):
        if current_param == 'region':
            L = ['@prompt', '@auto']
            pubLocations = rClient.get_application_publish_locations(self.appId)
            for p in pubLocations:
                L.append(p['regionName'])
            completions = [a for a in L
                           if a.startswith(text)]
        elif current_param == 'startAllVms':
            completions = [a for a in ['true', 'false']
                           if a.startswith(text)]
        else:
            completions = []
        if len(completions) == 1:
            return [completions[0] + ' ']
        else:
            return completions
    
    def ui_command_start(self):
        """
        Start a stopped application.
        
        Attempts to start all VMs in the application.
        """
        if not self.confirm_app_is_published():
            return
        if not is_admin():
            # Check that we don't have more started VMs than we should
            totalActiveVms = get_num_learner_active_vms(user)
            if totalActiveVms >= rOpt.maxLearnerActiveVms:
                print(c.red("\nYou have reached or exceeded the maximum number ({}) of active VMs!\n"
                            .format(rOpt.maxLearnerActiveVms)))
                print("Stop a VM (or a whole application) and then try this again")
                return
        # Start out by setting autostop
        self.extend_autostop(minutes=defaultAppExpireTime)
        try:
            rClient.start_application(self.appId)
        except:
            print(c.red("\nProblem starting application!\n"))
            raise
        print(c.yellow("\nApplication now starting"))
        rCache.purge_app_cache(self.appId)
        self.loop_query_status(desiredState='STARTED')
    
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
        self.extend_autostop(minutes=defaultAppExpireTime)
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
    
    def print_def(self):
        """Pretty-print vm JSON in pager."""
        pager("JSON definition for VM '{}' in APPLICATION '{}'\n".format(self.vmName, self.appName) +
              ui.prettify_json(rClient.get_vm(self.appId, self.vmId, aspect='deployment')))
    
    def ui_command_print_def(self, outputFile='@pager'):
        """
        Pretty-print VM JSON in pager or export to *outputFile*.
        
        Optionally specify *outputFile* as a relative or absolute path on the
        local system (tab-completion available).
        """
        print()
        outputFile = self.ui_eval_param(outputFile, 'string', '@pager')
        if outputFile == '@pager':
            self.print_def()
        else:
            try:
                ui.prepare_file_for_writing(outputFile)
            except:
                return
            try:
                with open(outputFile, 'w') as f:
                    json.dump(rClient.get_vm(self.appId, self.vmId, aspect='deployment'), f, indent=4)
            except IOError as e:
                print(c.RED("Problem writing VM definition for '{}' in APP '{}'\n"
                            "  {}\n".format(self.vmName, self.appName, e)))
                return
            print(c.green("Exported VM definition to file: '{}'\n".format(outputFile)))
    
    def ui_complete_print_def(self, parameters, text, current_param):
        if current_param != 'outputFile':
            return []
        completions = complete_path(text, S_ISREG)
        if len(completions) == 1 and not completions[0].endswith('/'):
            completions = [completions[0] + ' ']
        return completions
    
    def ui_command_start(self):
        """
        Start a stopped VM.
        
        The start, Stop, & restart commands all rely on the guest OS correctly
        handling ACPI events. If ACPI is disabled in the kernel (acpi=off) or
        the appropriate process isn't listening (RHEL6: acpid / RHEL7: systemd),
        the guest will gleefully ignore the request.
        """
        if not self.parent.parent.confirm_app_is_published():
            return
        if not self.confirm_vm_is_state('STOPPED'):
            return
        self.parent.parent.extend_autostop(minutes=defaultAppExtendTime)
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
        if not self.parent.parent.confirm_app_is_published():
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
        if not self.parent.parent.confirm_app_is_published():
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
        if not self.parent.parent.confirm_app_is_published():
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
        if not self.parent.parent.confirm_app_is_published():
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
        if not self.parent.parent.confirm_app_is_published():
            return
        try:
            rClient.repair_vm(self.appId, self.vmId)
        except:
            print(c.red("\nProblem repairing VM!\n"))
            raise
        print(c.yellow("\nAPI 'repair' call was sent; check VM status\n"))
        rCache.purge_app_cache(self.appId)
