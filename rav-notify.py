#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from datetime import datetime
from getpass import getpass
import argparse
import yaml
import json
import subprocess
import time
import sys
import os

# Custom modules
import string_ops
from ui_methods import get_timestamp_proximity, sanitize_timestamp
try:
    import ravello_sdk
    ravello_sdk.is_rsaw_sdk()
except:
    print("Missing proper version of required python module (rsaw's ravello_sdk)\n"
          "Get it from https://github.com/ryran/python-sdk/blob/ravshello-stable/lib/ravello_sdk.py\n")
    raise

# Globals
rClient = rOpt = c = appnamePrefix = None


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


def debug(*objs):
    """Print *objs* to stderr."""
    if rOpt.enableDebug:
        print("DEBUG:", *objs, file=sys.stderr)


def update_myAppIds(myAppIds=[]):
    """Refresh global myAppIds list by querying for my applications."""
    for app in rClient.get_applications(): 
        if app['name'].startswith(appnamePrefix) and not app['id'] in myAppIds:
            myAppIds.append(app['id'])
    debug("Watching for events on app ids:", myAppIds)
    return myAppIds


def extend_app_autostop(appId, appName, minutes=30):
    """Extend the expiration time of app *appId* by *minutes*."""
    req = {'expirationFromNowSeconds': minutes * 60}
    try:
        rClient.set_application_expiration(appId, req)
    except:
        cmd = [
            'zenity',
            '--error',
            '--title',
            "Extending auto-stop failed!",
            '--text',
            "Failure to extend application auto-stop timer of\n\n" +
             "{}\n\nYou should extend it manually in ravshello".format(appName),
             ]
        subprocess.check_call(cmd)
    else:
        cmd = [
            'notify-send',
            '--urgency',
            'low',
            "App auto-stop extended ({})".format(appName),
            "Application auto-stop timer set for {} minutes from now".format(minutes),
            ]
        subprocess.check_call(cmd)


def act_on_imminent_app_expiration(runningApps=[], thresholdSecs=5*60,
        extendTimeMins=30):
    """Iterate over *runningApps* to see if any will expire in < *thresholdSecs*.
    
    Expects a list of app dicts as the first param.
    Keys that are checked:
        id
        name
        expirationTime
    """
    for app in runningApps:
        proximity = get_timestamp_proximity(app['expirationTime'])
        if proximity > 0 and proximity < thresholdSecs:
            debug("App {} expiration proximity: {}s -- within warning threshold of {}s!".format(app['name'], proximity, thresholdSecs))
            tstamp = datetime.fromtimestamp(
                app['expirationTime']
                ).strftime("%H:%M:%S")
            titleText = "APP_EXPIRATION_IMMINENT"
            dialogText = (
                "Application '{}'\\n"
                "will shut down at {}. Extend auto-stop timer by {} mins?"
                ).format(app['name'], tstamp, extendTimeMins)
            try:
                # Try to create dialog w/zenity (GNOME).
                cmd = [
                    'zenity', '--question', '--title', titleText,
                    '--text', dialogText
                    ]
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as e:
                # A "yes" was not answered w/zenity.
                if e.returncode == 1:
                    # A definitive "no" was answered w/zenity.
                    continue
                else:
                    # Some other error w/zenity (missing cmd maybe).
                    try:
                        # Try to create dialog w/kdialog (KDE).
                        cmd = [
                            'kdialog', '--title', titleText,
                            '--warningyesno', dialogText
                            ]
                        subprocess.check_call(cmd)
                    except subprocess.CalledProcessError as e:
                        # A "yes" was not answered w/kdialog.
                        if e.returncode == 1:
                            # A definitive "no" was answered w/kdialog.
                            continue
                        else:
                            # Some other error w/kdialog (missing cmd maybe).
                            dialogText = (
                                "Application will shut down when auto-stop "
                                "timer reaches 0 at {}. Use "
                                "extend_app_autostop command to get more time."
                                "PS: Install zenity (GNOME) or kdialog (KDE) "
                                "to get interactive notifications."
                                ).format(tstamp)
                            cmd = [
                                'notify-send', '--urgency', 'critical',
                                titleText, dialogText
                                ]
                            subprocess.check_call(cmd)
                            continue
            # Reaching this point means user answered yes to zenity or kdialog.
            extend_app_autostop(app['id'], app['name'], extendTimeMins)
        else:
            debug("App {} expiration proximity: {}s -- OK".format(app['name'], proximity))


def main(argparseOptions):
    
    global c, rOpt, appnamePrefix, rClient
    rOpt = argparseOptions
    c = string_ops.Printer(rOpt.enableColor)
    runningApps = []
    timestamps = []
    
    try:
        with open(os.devnull, 'w') as devnull:
            subprocess.check_call(['notify-send', '--version'], stdout=devnull)
    except:
        print(c.RED("Unable to launch notify-send command!",
                    "We cannot notify you of events without libnotify installed"))
        sys.exit(2)
    
    try:
        with open(os.path.expanduser(rOpt.configFile)) as f:
            cfg = yaml.safe_load(f)
    except:
        print(c.yellow(
            "Note: unable to read configFile '{}'; using defaults"
            .format(rOpt.configFile)))
        nick = user = passwd = messg = events = None
    else:
        nick   = cfg.get('nickname', None)
        user   = cfg.get('ravelloUser', None)
        passwd = cfg.get('ravelloPass', None)
        messg  = cfg.get('unableToLoginAdditionalMsg', None)
        events = cfg.get('eventsOfInterest', None)
    
    if rOpt.kerberos:
        appnamePrefix = 'k:' + rOpt.kerberos + '__'
    elif nick:
        appnamePrefix = 'k:' + nick + '__'
    else:
        appnamePrefix = ''
    
    lackingCreds = False
    
    if not rOpt.ravelloUser:
        if user:
            rOpt.ravelloUser = user
        elif sys.stdout.isatty():
            rOpt.ravelloUser = get_username(c.CYAN("Enter Ravello username: "))
        else:
            lackingCreds = True
    
    if not rOpt.ravelloPass:
        if passwd:
            rOpt.ravelloPass = passwd
        elif sys.stdout.isatty():
            rOpt.ravelloPass = get_passphrase(c.CYAN("Enter Ravello passphrase: "))
        else:
            lackingCreds = True
    
    if lackingCreds:
        cmd = [
            'notify-send', '--urgency', 'critical',
            "rav-notify missing Ravello credentials!",
            "You must either populate ~/.ravshello/ravshello.conf, run " +
            "rav-notify with -u & -p options, or run rav-notify from a " +
            "terminal so it can prompt you for user/pass.",
            ]
        subprocess.check_call(cmd)
        sys.exit(3)
    
    rClient = ravello_sdk.RavelloClient()
    try:
        # Try to log in.
        rClient.login(rOpt.ravelloUser, rOpt.ravelloPass)
    except:
        if sys.stdout.isatty():
            print(c.RED("Logging in to Ravello failed!"))
            print("\nRe-check your username and password.")
            if messg: print(messg)
        else:
            cmd = [
                'notify-send', '--urgency', 'critical',
                "rav-notify failed to log in to Ravello!",
                "Re-check your username and password.",
                ]
            subprocess.check_call(cmd)
        sys.exit(5)
    
    cmd = [
        'notify-send', '--urgency', 'low',
        "rav-notify monitoring Ravello events",
        "Any events of interest (app timeouts or deletions, vms being " +
        "started or stopped) will trigger further notifications",
        ]
    subprocess.check_call(cmd)
    
    if events:
        eventsOfInterest = events
    else:
        eventsOfInterest = [
            'APP_TIMEOUT_AUTO_STOPPING',
            'APP_TIMEOUT_AUTO_STOPPED',
            'APPLICATION_TIMER_RESET',
            'APPLICATION_DELETED',
            'VM_STOPPED',
            'VM_STARTED',
            'VM_SNAPSHOTTING_AFTER_STOP',
            'VM_FINISHED_SNAPSHOTTING',
            ]
    
    debug("Event triggers:\n{}\n".format("\n".join(eventsOfInterest)))
    
    urgency = {
        'INFO': "low",
        'WARN': "normal",
        'ERROR': "critical",
        }
    
    # Build a list of app ids we should pay attention to.
    myAppIds = update_myAppIds()
    
    for appId in myAppIds:
        app = rClient.get_application(appId, aspect='properties')
        try:
            # Grab expiration time for all of my deployed apps.
            expirationTime = app['deployment']['expirationTime']
        except:
            continue
        else:
            a = {
                'id': appId,
                'name': app['name'].replace(appnamePrefix, ''),
                'expirationTime': sanitize_timestamp(expirationTime),
                }
            runningApps.append(a)
    
    # Run forever-loop to watch for notifications or expiring apps.
    while 1:
        
        # Run check to see if any apps are about to expire.
        act_on_imminent_app_expiration(runningApps)
        
        myEvents = []
        # Set lower bound to 5 minutes ago, upper bound to right now.
        # Unusual manipulation present because Ravello expects timestamps to
        # include thousandths of a sec, but not as floating-point.
        start = time.time() - (5*60 + rOpt.refreshInterval)
        start = int("{:.3f}".format(start).replace('.', ''))
        end = int("{:.3f}".format(time.time()).replace('.', ''))
        query = {
            'dateRange': {
                'startTime': start,
                'endTime': end,
                },
            }
        try:
            # Perform our search.
            results = rClient.search_notifications(query)
        except ravello_sdk.RavelloError as e:
            if e.args[0] == 'request timeout':
                # Timeout, so try one more time.
                results = rClient.search_notifications(query)
        try:
            # Results are returned in reverse-chronological order.
            for event in reversed(results['notification']):
                try:
                    # Only deal with events we have not seen before that relate
                    # to one of myAppIds.
                    if (any(appId == event['appId'] for appId in myAppIds) and 
                            event['eventTimeStamp'] not in timestamps):
                        myEvents.append(event)
                except:
                    pass
        except:
            pass
        
        # Iterate over events relevant to my apps.
        for event in myEvents:
            
            if any(etype in event['eventType'] for etype in eventsOfInterest):
                # Get application data if event of interest.
                try:
                    app = rClient.get_application(
                        event['appId'], aspect='properties')
                except KeyError:
                    # Will fail if event is not about an app, i.e.: on user login.
                    continue
            else:
                continue
            
            # Add unique timestamp for this event to our list, to prevent acting
            # on it in a subsequent loop.
            timestamps.append(event['eventTimeStamp'])
            
            try:
                appName = app['name'].replace(appnamePrefix, '')
            except TypeError:
                # Will fail if app was deleted.
                appName = ''
            
            if event['eventType'] == 'APPLICATION_TIMER_RESET':
                try:
                    # Grab expiration time if app is deployed.
                    expirationTime = app['deployment']['expirationTime']
                except:
                    # (app isn't deployed)
                    pass
                else:
                    expirationTime = sanitize_timestamp(expirationTime)
                    for a in runningApps:
                        # Try to find the app by id in our existing list.
                        if a['id'] == app['id']:
                            # Update the app's expirationTime timestamp.
                            a['expirationTime'] = expirationTime
                            break
                    else:
                        # If the appId for the APPLICATION_TIMER_RESET event isn't
                        # present in our runningApps list, we need to add it.
                        a = {
                            'id': app['id'],
                            'name': appName,
                            'expirationTime': expirationTime,
                            }
                        runningApps.append(a)
            else:
                # Event type is anything but APPLICATION_TIMER_RESET.
                tstamp = datetime.fromtimestamp(
                    sanitize_timestamp(timestamps[-1])
                    ).strftime("%H:%M:%S")
                if appName:
                    appName = " ({})".format(appName)
                msg = event['eventProperties'][0]['value'].replace(appnamePrefix, '')
                cmd = [
                    'notify-send',
                    '--urgency',
                    urgency[event['notificationLevel']],
                    "{}{}".format(event['eventType'], appName),
                    "[{}] {}".format(tstamp, msg),
                    ]
                subprocess.check_call(cmd)
        
        if rOpt.enableDebug and sys.stdout.isatty():
            i = rOpt.refreshInterval
            while i >= 0:
                print(c.REVERSE("{}".format(i)), end='')
                sys.stdout.flush()
                time.sleep(1)
                print('\033[2K', end='')
                i -= 1
            print()
        else:
            time.sleep(rOpt.refreshInterval)

        myAppIds = update_myAppIds(myAppIds)


if __name__ == "__main__":
    
    prog = 'rav-notify'
    description = "Listen for Ravello events relevant to your appplications"    
    p = argparse.ArgumentParser(prog=prog, description=description, 
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('-u',  dest='ravelloUser', metavar='USER', default='',
        help="Explicitly specify Ravello username (will automatically prompt " +
             "for a passphrase)")
    p.add_argument('-p', dest='ravelloPass', metavar='PASSWD', default='',
        help="Explicitly specify a Ravello user password on the command-line " +
             "(unsafe on multi-user system)")
    p.add_argument('-k', dest='kerberos', metavar='KERBEROS', default='',
        help="Explicitly specify a kerberos username to use for app-filtering " +
             "(Without this, {} will listen for events on all apps)".format(prog))
    p.add_argument('-f', dest='configFile', metavar='CFGFILE',
        default='~/.ravshello/config.yaml',
        help="Explicitly specify path to a yaml config file (Defaults to " +
             "~/.ravshello/config.yaml")
    p.add_argument('-i', dest='refreshInterval', metavar='SECONDS', default=50,
        type=int, help="Tweak default refresh interval (50 sec) to your choosing")
    p.add_argument('-n', '--nocolor', dest='enableColor', action='store_false',
        help="Disable all color terminal enhancements")
    p.add_argument('-d', '--debug', dest='enableDebug', action='store_true',
        help="Enable printing extra details to stdout & stderr")
    
    # Parse args out to namespace
    rOpt = p.parse_args()
    
    try:
        main(rOpt)
    except KeyboardInterrupt:
        print()
        sys.exit(0)
