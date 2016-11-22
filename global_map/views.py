import re
import os
import math
import pytz
from datetime import datetime, timedelta, date as datetime_date
import json
from django.views.generic import TemplateView, View
from global_map.models import Clan, ProvinceTag, ProvinceAssault, ProvinceBattle
import urllib2
from collections import OrderedDict, defaultdict
from django.conf import settings
from retrying import retry
import wargaming
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, QueryDict
from django.db.models import Count, Q

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
wgn = wargaming.WGN(settings.WARGAMING_KEY, language='ru', region='ru')


class TagView(View):
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(TagView, self).dispatch(request, *args, **kwargs)

    def post(self, *args, **kwargs):
        province_id = self.request.POST.get('province_id')
        tag = self.request.POST.get('tag')
        date = self.request.POST.get('date')
        ProvinceTag.objects.create(date=date, province_id=province_id, tag=tag)
        return JsonResponse({'ok': 'ok'})

    def delete(self, *args, **kwargs):
        body = QueryDict(self.request.body)
        province_id = body.get('province_id')
        tag = body.get('tag')
        date = body.get('date')
        ProvinceTag.objects.filter(date=date, tag=tag,
                                   province_id=province_id).delete()
        return JsonResponse({'ok': 'ok'})


class ListBattles(TemplateView):
    template_name = 'list_battles.html'
    cached_time = None


class ListBattlesJson(View):
    def get(self, *args, **kwargs):
        date = kwargs.get('date')
        clan = Clan.objects.get(pk=35039)
        if date:
            date = datetime_date(*[int(i) for i in date.split('-')])
            assaults = ProvinceAssault.objects.filter(date=date).annotate(ccount=Count('clans')) \
                .filter(ccount__gt=0).filter(Q(battles__clan_a=clan) | Q(battles__clan_b=clan))
        else:
            date = datetime.now().date()
            assaults = ProvinceAssault.objects.filter(date=date).annotate(ccount=Count('clans')) \
                .filter(ccount__gt=0).filter(Q(clans=clan) | Q(current_owner=clan))

        times = []
        for assault in assaults:
            times.extend(assault.planned_times)

        assaults = [assault.as_clan_json(clan) for assault in assaults]

        if times:
            min_time = min(times)
            min_time = min_time.replace(minute=min_time.minute - min_time.minute % 30)
            max_time = max(times)
        else:
            min_time = datetime.now().replace(hour=15, minute=00)
            max_time = datetime.now().replace(hour=2, minute=00) + timedelta(days=1)

        return JsonResponse({
            'time_range': [min_time, max_time],
            'assaults': sorted(
                assaults,
                key=lambda v: (v['province_info']['prime_time'].minute == 15, v['province_info']['prime_time'])
            ),
        })
