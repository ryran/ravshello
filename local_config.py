# -*- coding: utf-8 -*-
from os import path

class RavshelloUI:
    """Directives used by user_interface and auth_local modules
    
    • If present, sshKeyFile is integrated into the ssh command reported to the
      user by ravshello's query_app_status command
      
    • If present, nickname will be used as the ravshello 'user', overriding the
      default behavior of determining this from the system user (note that this
      nickname directive can in turn be overriden by the cmdline --nickname opt)
    """
    sshKeyFile = None    # e.g.: "/etc/ravshello_ssh_key"
    nickname = None      # e.g.: "rsawaroha"
    # If a key *is* specified, but doesn't exist, set it back to None
    if sshKeyFile and not path.exists(sshKeyFile): sshKeyFile = None


class RavelloLogin:
    """Directives used by auth_ravello module
    
    Ravello acct info needs to be either here or passed via cmdline.
    """
    ravelloUser = None   # e.g.: "rsaw@example.com"
    ravelloPass = None   # e.g.: "r5aw'z cra2y passw0rD"
    unableToLoginAdditionalMsg = None     # e.g.: "Call Bob in IT @ 555.1234"
