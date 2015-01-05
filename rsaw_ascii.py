# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

# Modules from standard library
from __future__ import print_function
    
def replace_bad_chars_with_underscores(string):
    """Perform some simple character translation/substitution on *string*."""
    return string.replace('@', '_').replace(' ', '_').replace('+', '_')


class AsciiColors:
    """Essentially a container for ascii colorization methods."""
    
    def __init__(self, enableAsciiColors=True):
        self.enableColor = enableAsciiColors
    
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
