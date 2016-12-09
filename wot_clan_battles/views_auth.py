import six

from django.http import HttpResponseRedirect
from django.shortcuts import reverse
from django.conf import settings

from openid.consumer import consumer

import wargaming

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')


def auth_callback(request):
    oidconsumer = consumer.Consumer(request.session, None)
    url = 'http://%s%s' % (request.META['HTTP_HOST'], reverse('auth_callback'))
    result = oidconsumer.complete(request.GET, url)
    if result.status == consumer.SUCCESS:
        identifier = result.getDisplayIdentifier()
        print identifier
        user_id, username = six.moves.urllib_parse.urlparse(identifier).path.split('/')[2].split('-')
        request.session['user_id'] = user_id
        request.session['username'] = username
        request.session['user_clan_id'] = wot.account.info(account_id=user_id)[str(user_id)]['clan_id']
    return HttpResponseRedirect('/')


def auth_login(request):
    oidconsumer = consumer.Consumer(dict(request.session), None)
    openid_request = oidconsumer.begin(u'http://ru.wargaming.net/id/openid/')
    trust_root = 'http://%s' % request.META['HTTP_HOST']
    return_to = '%s%s' % (trust_root, reverse('auth_callback'))
    redirect_to = openid_request.redirectURL(trust_root, return_to, immediate=False)
    return HttpResponseRedirect(redirect_to)
