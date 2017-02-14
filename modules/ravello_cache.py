# -*- coding: utf-8 -*-
# Copyright 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from time import time, sleep

# Custom modules
from . import ui_methods as ui

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
            if ui.get_timestamp_proximity(ts) < -120:
                self.update_bp_cache()
        if bpId in self.bpCache:
            return self.bpCache[bpId]
        else:
            return None
    
    def get_bps(self, myOrgOnly=False):
        try:
            ts = self._bpCache_tstamp
        except:
            self.update_bp_cache()
        else:
            if ui.get_timestamp_proximity(ts) < -120:
                self.update_bp_cache()
        if myOrgOnly:
            return [bp for bp in self.bpCache.values() if self.get_user(bp['ownerDetails']['userId'])]
        else:
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
    
    def get_app(self, appId, aspect=None):
        if appId not in self.appCache or ui.get_timestamp_proximity(self.appCache[appId]['ts']) < -120:
            self.update_app_cache(appId)
        if aspect:
            return self.appCache[appId]['definition'][aspect]
        else:
            return self.appCache[appId]['definition']
    
    def get_vm(self, appId, vmId, aspect):
        if appId not in self.appCache or ui.get_timestamp_proximity(self.appCache[appId]['ts']) < -120:
            self.update_app_cache(appId)
        for vm in self.appCache[appId]['definition'][aspect]['vms']:
            if vm['id'] == vmId:
                return vm
    
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
            if ui.get_timestamp_proximity(ts) < -120:
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
            if ui.get_timestamp_proximity(ts) < -120:
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
            if ui.get_timestamp_proximity(self.alertCache['_timestamp']) < -120:
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
            if ui.get_timestamp_proximity(ts) < -120:
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
            if ui.get_timestamp_proximity(ts) < -120:
                self.update_share_cache()
        return self.shareCache.values()
