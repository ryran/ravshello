# -*- coding: utf-8 -*-
from os import path

class RavshelloUI:
    """Directives used by user_interface module
    
    • If present, sshKeyFile is integrated into the ssh command reported to the
      user by ravshello's query_app_status command
    """
    sshKeyFile = None    # e.g.: "/etc/ravshello_ssh_key"
    
    # If a key *is* specified, but ceases to exist, let's auto-set back to None
    if sshKeyFile and not path.exists(sshKeyFile):
        sshKeyFile = None


class RavelloLogin:
    """Directives used by auth_ravello module
    
    Ravello acct info needs to be either here or passed via cmdline.
    """
    ravelloUser = None   # e.g.: "bob@example.com"
    ravelloPass = None   # e.g.: "b0b'z cra2y passw0rD"
    unableToLoginAdditionalMsg = None     # e.g.: "Call Bob in IT @ 555.1234"
