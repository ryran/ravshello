# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
from time import sleep
from re import sub


class Printer(object):
    """Provide some printer methods & string colorization methods."""
    
    def __init__(self, enableColor=True, enableVerboseMessages=True):
        """Configure if color should be enabled, verbose messages printed.
        
        We also store some details for the replace_bad_chars method.
        """
        self.enableColor = enableColor
        self.enableVerbose = enableVerboseMessages
    
    def slow_print(self, string, interval=.02):
        """Print input *string* 1 char at a time w/ *interval* secs between."""
        for char in string:
            sleep(interval)
            print(char, end='')
            stdout.flush()
        print()
    
    def replace_bad_chars_with_underscores(self, string,
            pattern='[^A-Za-z0-9:_.-]', repl='_', count=0):
        """Perform some simple character substitution on *string*."""
        return sub(pattern, repl, string, count)
    
    def verbose(self, message, end=None):
        """Print *message* in magenta only if verboseMessages is True."""
        if self.enableVerbose:
            if end is not None:
                print(self.magenta(message), end=end)
            else:
                print(self.magenta(message))
    
    def REVERSE(self, txt):
        """Return text in reverse (& bolded)."""
        if self.enableColor:
            return '\033[1;1m' + '\033[7m' + str(txt) + '\033[0m'
        return txt
    
    def BOLD(self, txt):
        """Return text in bold."""
        if self.enableColor:
            return '\033[1;1m' + str(txt) + '\033[0m'
        return txt
    
    def red(self, txt):
        """Return text in red."""
        if self.enableColor:
            return '\033[31m' + str(txt) + '\033[0m'
        return txt
    
    def RED(self, txt):
        """Return text in bolded red."""
        if self.enableColor:
            return '\033[1;1m' + '\033[31m' + str(txt) + '\033[0m'
        return txt
    
    def bgRED(self, txt):
        """Return text in red background (& bolded)."""
        if self.enableColor:
            return '\033[1;1m' + '\033[41m' + str(txt) + '\033[0m'
        return txt
    
    def yellow(self, txt):
        """Return text in yellow."""
        if self.enableColor:
            return '\033[33m' + str(txt) + '\033[0m'
        return txt
    
    def YELLOW(self, txt):
        """Return text in bolded yellow."""
        if self.enableColor:
            return '\033[1;1m' + '\033[33m' + str(txt) + '\033[0m'
        return txt
    
    def blue(self, txt):
        """Return text in blue."""
        if self.enableColor:
            return '\033[34m' + str(txt) + '\033[0m'
        return txt
    
    def BLUE(self, txt):
        """Return text in bolded blue."""
        if self.enableColor:
            return '\033[1;1m' + '\033[34m' + str(txt) + '\033[0m'
        return txt
    
    def bgBLUE(self, txt):
        """Return text in blue background (& bolded)."""
        if self.enableColor:
            return '\033[1;1m' + '\033[44m' + str(txt) + '\033[0m'
        return txt
    
    def green(self, txt):
        """Return text in green."""
        if self.enableColor:
            return '\033[32m' + str(txt) + '\033[0m'
        return txt
    
    def GREEN(self, txt):
        """Return text in bolded green."""
        if self.enableColor:
            return '\033[1;1m' + '\033[32m' + str(txt) + '\033[0m'
        return txt
    
    def cyan(self, txt):
        """Return text in cyan."""
        if self.enableColor:
            return '\033[36m' + str(txt) + '\033[0m'
        return txt
    
    def CYAN(self, txt):
        """Return text in bolded cyan."""
        if self.enableColor:
            return '\033[1;1m' + '\033[36m' + str(txt) + '\033[0m'
        return txt
    
    def magenta(self, txt):
        """Return text in magenta."""
        if self.enableColor:
            return '\033[35m' + str(txt) + '\033[0m'
        return txt
    
    def MAGENTA(self, txt):
        """Return text in bolded magenta."""
        if self.enableColor:
            return '\033[1;1m' + '\033[35m' + str(txt) + '\033[0m'
        return txt
