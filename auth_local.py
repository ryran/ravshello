# -*- coding: utf-8 -*-
# Copyright 2014 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

from __future__ import print_function
from pwd import getpwuid
from os import getuid

def authorize_user(opt):
    return getpwuid(getuid()).pw_name
