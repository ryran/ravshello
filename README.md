ravshello
=========

Do you have an account with ravellosystems.com?
Do you want to use the command-line to manage your account?
**If yes, then check this out.**

Proper python packaging not in place yet, so here's some get-started instructions:

```
git clone https://github.com/ryran/ravshello.git ~/ravshello
mkdir ~/bin
ln -sv ~/ravshello/ravshello.py ~/bin/ravshello
ln -sv ~/ravshello/rav-notify.py ~/bin/rav-notify
wget -P ~/ravshello https://raw.githubusercontent.com/ryran/python-sdk/experimental/lib/ravello_sdk.py
ravshello
```

After that, you can optionally populate the config file to avoid typing user/pass all the time:

```
cp -v ~/ravshello/config.yaml ~/.ravshello/
vim ~/.ravshello/config.yaml
```

You can also optionally run `rav-notify` to get GUI notifications for your apps.


screenshots
===========

![help page](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.help.png)

![initial login, create/publish app](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.create_publish.png)

![ssh to & delete published app](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.ssh_delete.png)

![blueprints](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.blueprints.png)

![non-interactive w/blueprints backup](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.non_interactive_bpbackup.png)

![register user alerts](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.events.png)

![search notifications](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.eventsregister_search_notifications.png)

![billing charges](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.billing.png)

![visibility on all apps in org](http://people.redhat.com/rsawhill/ravshello/stock-ravshello.global_apps.png)
