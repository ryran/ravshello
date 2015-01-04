# -*- coding: utf-8 -*-
# Copyright 2015 Ravshello Authors
# License: Apache License 2.0 (see LICENSE or http://apache.org/licenses/LICENSE-2.0.html)

from __future__ import print_function
import pwd
import os

def authorize_user(opt):
    return pwd.getpwuid(os.getuid()).pw_name
