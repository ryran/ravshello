# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from getpass import getpass
from datetime import date
from os import path, makedirs, chmod, remove
from time import time
from sys import stdout
import json


def get_passphrase(prompt="Enter passphrase: ", defaultPass=None, confirm=False):
    """Prompt for a passphrase, allowing pre-populated *defaultPass*."""
    pwd1 = getpass(prompt)
    while not len(pwd1):
        if defaultPass:
            return defaultPass
        else:
            print("You must enter a passphrase")
            pwd1 = getpass(prompt)
    if confirm:
        print("Re-enter pass to confirm")
        pwd2 = getpass(prompt)
        while not pwd1 == pwd2:
            print("Second passphrase did not match the first!")
            pwd2 = getpass(prompt)
    return pwd1


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


def save_str_to_file(outfile, string, perms=0600):
    """Save *string* to *outfile*"""
    try:
        with open(outfile, 'w') as f:
            f.write(str(string))
        chmod(outfile, perms)
    except:
        pass


def prompt_for_number(prompt, endRange=None, startRange=0, defaultNumber=None):
    """Prompt for & require a positive natural number or a number in a range."""
    while 1:
        try:
            if defaultNumber is None:
                n = int(raw_input(prompt))
            else:
                n = raw_input(prompt)
                if len(n):
                    n = int(n)
                else:
                    n = int(defaultNumber)
            if endRange is None:
                if n > 0:
                    break
            else:
                if startRange < endRange or startRange == endRange:
                    r = range(startRange, endRange + 1)
                else:
                    r = range(endRange, startRange + 1)
                if n in r:
                    break
            raise ValueError
        except ValueError:
            print("Not a valid number! Try again")
    return n


def prettify_json(input):
    """Convert dictionary-like json to multiline indented output."""
    return str(json.dumps(input, indent=4))


def iterate_json_keys_for_value(jsonObj, key, value):
    """Return True if *jsonObj* contains a toplevel *key* set to *value*."""
    for i in jsonObj:
        if i[key] == value:
            return True
    return False


def sanitize_timestamp(ts):
    """Insert period into 3rd-from-last place of funky Ravello timestamp."""
    ts = str(ts)
    return float(ts[:-3] + '.' + ts[-3:])


def get_timestamp_proximity(timeStamp, now=None):
    """Return proximity in seconds (as int) between *timeStamp* and now.
    
    The param *timeStamp* should be a float representing number of seconds since
    UNIX epoch (as returned by time.time()).
    
    The param *now* can be used to explicitly specify the "now" time -- i.e., to
    compare two timestamps, instead of comparing a timestamp with current time.
    
    Since Ravello timestamps are strings which include thousands of a sec
    without any delimiting period, we pass non-floats to the
    sanitize_timestamp() to get fixed up.
    
    Return values converted to int.
    Positive values indicate future; negative, past.
    """
    if not now:
        now = time()
    if not isinstance(timeStamp, float):
        timeStamp = sanitize_timestamp(timeStamp)
    if not isinstance(now, float):
        now = sanitize_timestamp(now)
    return int(round(timeStamp - now))


class RavelloCache(object):
    """Provide a way to locally-cache lookups of apps, users, events, etc."""
    
    def __init__(self, rClient):
        """Initialize using *client*, an instance of ravello_sdk.RavelloClient()."""
        self.r = rClient
        self.bpCache = {}
        self.appCache = {}
        self.userCache = {}
        self.alertCache = {}
        self.shareCache = {}
    
    def update_bp_cache(self):
        self._bpCache_tstamp = time()
        self.bpCache = {}
        for b in self.r.get_blueprints():
            self.bpCache[b['id']] = b
    
    def purge_bp_cache(self):
        self.bpCache = {}
    
    def get_bp(self, bpId):
        bpId = int(bpId)
        try:
            ts = self._bpCache_tstamp
        except:
            self.update_bp_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_bp_cache()
        if bpId in self.bpCache:
            return self.bpCache[bpId]
        else:
            return None
    
    def get_bps(self):
        try:
            ts = self._bpCache_tstamp
        except:
            self.update_bp_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_bp_cache()
        return self.bpCache.values()
    
    def update_app_cache(self, appId=None):
        if appId:
            self.appCache[appId] = {}
            self.appCache[appId]['definition'] = self.r.get_application(appId)
            self.appCache[appId]['ts'] = time()
        else:
            for appId in self.appCache:
                try:
                     a = self.r.get_application(appId)
                except:
                    continue
                else:
                    self.appCache[appId] = {}
                    self.appCache[appId]['definition'] = a
                    self.appCache[appId]['ts'] = time()
    
    def purge_app_cache(self, appId=None):
        if appId:
            if appId in self.appCache:
                del self.appCache[appId]
        else:
            self.appCache = {}
    
    def get_app(self, appId):
        if appId not in self.appCache or get_timestamp_proximity(self.appCache[appId]['ts']) < -60:
            self.update_app_cache(appId)
        return self.appCache[appId]['definition']
    
    def update_user_cache(self):
        self._userCache_tstamp = time()
        self.userCache = {}
        for u in self.r.get_users():
            self.userCache[u['id']] = u
    
    def purge_user_cache(self):
        self.userCache = {}
    
    def get_user(self, userId):
        try:
            ts = self._userCache_tstamp
        except:
            self.update_user_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_user_cache()
        if userId in self.userCache:
            return self.userCache[userId]
        else:
            return None
    
    def get_users(self):
        try:
            ts = self._userCache_tstamp
        except:
            self.update_user_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_user_cache()
        return self.userCache.values()
    
    def update_alert_cache(self):
        self.alertCache = {}
        for alert in self.r.get_alerts():
            a = {
                'userId': alert['userId'],
                'alertId': alert['id'],
                }
            try:
                self.alertCache[alert['eventName']].append(a)
            except:
                self.alertCache[alert['eventName']] = [a]
        self.alertCache['_timestamp'] = time()
    
    def purge_alert_cache(self):
        self.alertCache = {}
    
    def get_alerts_for_event(self, eventName):
        if not len(self.alertCache):
            self.update_alert_cache()
        if eventName in self.alertCache:
            if get_timestamp_proximity(self.alertCache['_timestamp']) < -120:
                self.update_alert_cache()
            return self.alertCache[eventName]
        else:
            return None
    
    def update_share_cache(self):
        self._shareCache_tstamp = time()
        self.shareCache = {}
        for s in self.r.get_shares():
            self.shareCache[s['id']] = s
    
    def purge_share_cache(self, shareId=None):
        if shareId:
            if shareId in self.shareCache:
                del self.shareCache[shareId]
        else:
            self.shareCache = {}
    
    def get_share(self, shareId):
        try:
            ts = self._shareCache_tstamp
        except:
            self.update_share_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_share_cache()
        if shareId in self.shareCache:
            return self.shareCache[shareId]
        else:
            return None
    
    def get_shares(self):
        try:
            ts = self._shareCache_tstamp
        except:
            self.update_share_cache()
        else:
            if get_timestamp_proximity(ts) < -120:
                self.update_share_cache()
        return self.shareCache.values()
    
    def get_application_details(self, app):
        """Return details for all VMs in application with ID *app*."""
        appDefinition = self.r.get_application(app, aspect='deployment')
        if not appDefinition['published']:
            return None, None, None
        vmDetails = []
        for vm in appDefinition['deployment']['vms']:
            vmDict = {
                'name': vm['name'],
                'state': vm['state'],
                'ssh': {
                    'port': '',
                    'fqdn': '',
                    },
                'vnc': '',
                'nics': [],
                'hostnames': [],
                }
            try:
                vmDict['hostnames'] = vm['hostnames']
            except:
                pass
            if vm['state'] == 'STARTED':
                try:
                    vmDict['vnc'] = self.r.get_vnc_url(app, vm['id'])
                except:
                    pass
                if vm.has_key('networkConnections'):
                    for interface in vm['networkConnections']:
                        i = {
                            'name': interface['name'],
                            'ip_Elastic': '',
                            'ip_Public': '',
                            'ip_Forwarder': '',
                            'ip_Private': '',
                            'ip_Additional': [],
                            'fqdn': '',
                            'services': [],
                            }
                        if interface['ipConfig']['hasPublicIp']:
                            try:
                                i['ip_Elastic'] = interface['ipConfig']['elasticIpAddress']
                            except:
                                i['ip_Public'] = interface['ipConfig']['publicIp']
                        elif interface['ipConfig'].has_key('publicIp'):
                            i['ip_Forwarder'] = interface['ipConfig']['publicIp']
                        if interface['ipConfig'].has_key('fqdn'):
                            i['fqdn'] = interface['ipConfig']['fqdn']
                        if interface['ipConfig'].has_key('autoIpConfig'):
                            i['ip_Private'] = interface['ipConfig']['autoIpConfig']['allocatedIp']
                        elif interface['ipConfig'].has_key('staticIpConfig'):
                            i['ip_Private'] = interface['ipConfig']['staticIpConfig']['ip']
                        if interface.has_key('additionalIpConfig'):
                            for addtlIp in interface['additionalIpConfig']:
                                if addtlIp.has_key('staticIpConfig'):
                                    i['ip_Additional'].append(addtlIp['staticIpConfig']['ip'])
                        if vm.has_key('suppliedServices'):
                            for service in vm['suppliedServices']:
                                if service['external'] and service['useLuidForIpConfig'] and interface['ipConfig']['id'] == service['ipConfigLuid'] and not service['name'].startswith('dummy'):
                                    if service['name'] == 'ssh' and not vmDict['ssh']['port']:
                                        vmDict['ssh']['port'] = " -p {}".format(service['externalPort'])
                                        vmDict['ssh']['fqdn'] = i['fqdn']
                                    s = {
                                        'name': service['name'],
                                        'externalPort': service['externalPort'],
                                        'protocol': service['protocol'],
                                        'portRange': service['portRange'],
                                        }
                                    i['services'].append(s)
                        vmDict['nics'].append(i)
            vmDetails.append(vmDict)
        try:
            expirationTime = sanitize_timestamp(appDefinition['deployment']['expirationTime'])
        except:
            expirationTime = None
        return vmDetails, appDefinition['deployment']['cloudRegion']['name'], expirationTime
