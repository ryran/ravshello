# -*- coding: utf-8 -*-
# Copyright 2015, 2016, 2017 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from getpass import getpass
from datetime import datetime, date
from os import path, makedirs, chmod, remove, environ
from time import time, sleep
from pydoc import pipepager
from tempfile import NamedTemporaryFile
from distutils.spawn import find_executable
from sys import stdout
import subprocess
import json
import re

# Custom modules
from . import cfg
from . import string_ops as c

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


def prompt_for_number(prompt, endRange=None, startRange=0, defaultNumber=None, numberList=None):
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
            if numberList:
                if n in numberList:
                    break
            elif endRange is None:
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


def print_obj(obj, desc, output='@EDITOR', tmpPrefix='', suffix='.json'):
    """Send *obj* to pager/terminal/subprocess/file."""
    tmpPrefix += '-'
    if suffix == '.json' and not isinstance(obj, str):
        obj = prettify_json(obj)
    if output == '@pager':
        print(c.yellow("Printing {} to pager . . .\n".format(desc)))
        pipepager(obj, cmd='less -R')
    elif output == '@term':
        print(c.yellow("Printing {} to terminal . . .\n".format(desc)))
        print(obj)
    elif output == '@EDITOR':
        if environ.has_key('RAVSH_EDITOR') and find_executable(environ['RAVSH_EDITOR']):
            cmd = environ['RAVSH_EDITOR']
        elif environ.has_key('EDITOR') and find_executable(environ['EDITOR']):
            cmd = environ['EDITOR']
        elif environ.has_key('DISPLAY') and find_executable('gvim'):
            cmd = 'gvim'
        elif find_executable('vim'):
            cmd = 'vim'
        else:
            print(c.yellow("Printing {} to pager . . .\n".format(desc)))
            pipepager(obj, cmd='less -R')
            return
        print(c.yellow("Saving {} to tmpfile & opening w/cmd '{}' . . .\n".format(desc, cmd)))
        tmp = NamedTemporaryFile(prefix=tmpPrefix, suffix=suffix, delete=False)
        tmp.write(obj)
        tmp.flush()
        subprocess.call([cmd, tmp.name])
    else:
        output = path.expanduser(output)
        if suffix:
            output += suffix
        try:
            prepare_file_for_writing(output)
        except:
            return
        try:
            with open(output, 'w') as f:
                f.write(obj)
        except IOError as e:
            print(c.RED("Problem exporting {} to file: '{}'\n"
                        "  {}\n".format(desc, output, e)))
            return
        print(c.green("Exported {} to file: '{}'\n".format(desc, output)))


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


def convert_ts_to_date(ts, showHours=True):
    """Convert a timestamp into absolute date string."""
    if not isinstance(ts, float):
        ts = sanitize_timestamp(ts)
    diff = ts - time()
    m, s = divmod(ts - time(), 60)
    expireDateTime = datetime.fromtimestamp(ts)
    if showHours:
        d = expireDateTime.strftime('%Y/%m/%d @ %H:%M')
    else:
        d = expireDateTime.strftime('%Y/%m/%d')
    return d


def expand_secs_to_ywdhms(seconds):
    seconds = int(seconds)
    intervals = (
        ('yrs',  31536000), # 60 * 60 * 24 * 365
        ('wks',  604800),   # 60 * 60 * 24 * 7
        ('days', 86400),    # 60 * 60 * 24
        ('hrs',  3600),     # 60 * 60
        ('mins', 60),
        ('secs', 1),
        )
    result = []
    for unit, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                unit = unit.rstrip('s')
            result.append("{} {}".format(value, unit))
    return ', '.join(result)

def validate_ipv4_addr(ipstring):
    """Ensure that string is a valid IPv4 address in decimal."""
    pieces = ipstring.split('.')
    if len(pieces) != 4:
        return False
    try:
        return all(0<=int(p)<256 for p in pieces)
    except ValueError:
        return False

def validate_mac_addr(macstring):
    """Ensure that string is a valid MAC address in standard format."""
    regexstr = "[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$"
    return re.match(regexstr, macstring.lower())
