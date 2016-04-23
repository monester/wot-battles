#!/usr/bin/env bash

#ssh-keygen -f "/home/m/.ssh/known_hosts" -R 139.59.134.211

REMOTE_IP=139.59.134.211

ssh $REMOTE_IP "apt-get update; apt-get -y install virtualenv python-all-dev python-pip nginx uwsgi uwsgi-plugin-python"

rsync -av --exclude=.git --exclude=build ../python-wargaming $REMOTE_IP:/var/www
REMOTE_IP=139.59.134.211
rsync -av --exclude=.git --exclude=venv --chown=www-data:www-data  `pwd` $REMOTE_IP:/var/www
