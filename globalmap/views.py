import re
import math
from datetime import datetime, timedelta
from django.views.generic import TemplateView
from models import Clan

from collections import OrderedDict, defaultdict
from django.conf import settings
from retrying import retry

import requests
from .models import Clan, Province


class ListBattles(TemplateView):
    template_name = 'list_battles.html'
    region = settings.DEFAULT_REGION

    def dispatch(self, request, *args, **kwargs):
        self.region = kwargs['region']
        res = super(ListBattles, self).dispatch(request, *args, **kwargs)
        return res

    def get_context_data(self, **kwargs):
        context = super(ListBattles, self).get_context_data(**kwargs)
        clan_tag = self.request.GET.get('tag', 'SMIRK')
        clan = Clan.get_or_create(clan_tag=clan_tag, region=self.region)
        clan_id = clan.clan_id
        province_list = defaultdict(lambda: [])  # list of all provinces we have any actions, by front
        owned_provinces = []                     # list of all owned provinces
        provinces_data = {}                      # provinces data

        wot = settings.WOT[self.region]
        data = clan.clan_battles()

        # prepare list of provinces to query
        for battle_type in ['battles', 'planned_battles']:
            for battle in data[battle_type]:
                province_list[battle['front_id']].append(battle['province_id'])

        # # fetch for clan owned provinces
        # clan_provinces = wot.globalmap.clanprovinces(clan_id=clan_id)[clan_id]
        # if clan_provinces:
        #     for own in clan_provinces:
        #         front_id = own['front_id']
        #         province_list[front_id].append(own['province_id'])
        #         owned_provinces.append(own['province_id'])
        #
        # # fetch for provinces data
        # for front_id in province_list.keys():
        #     plist = list(set(province_list[front_id]))  # make list unique
        #     if plist:
        #         for p in wot.globalmap.provinces(front_id=front_id, province_id=plist):
        #             provinces_data[p['province_id']] = p

        # **** Battle section *****
        provinces = {}

        # fill battles from battles screen on GlobalMap
        for battle_type in ['battles', 'planned_battles']:
            for battle in data[battle_type]:
                province_id = battle['province_id']
                provinces[province_id] = Province.objects.get(province_id=province_id, region=self.region)

        # # fill defences from owned battles
        # for own in owned_provinces:
        #     if own not in provinces and (provinces_data[own]['attackers'] or provinces_data[own]['competitors']):
        #         provinces[own] = Province(provinces_data[own], self.region)
        #
        # # fill attacks by land
        # neighbours_list = defaultdict(lambda: [])
        # for own in owned_provinces:
        #     for neighbor in provinces_data[own]['neighbours']:
        #         neighbours_list[provinces_data[own]['front_id']].append(neighbor)
        #
        # neighbours_data = {}
        # for front_id in neighbours_list.keys():
        #     plist = list(set(neighbours_list[front_id]))  # make list unique
        #     for p in wot.globalmap.provinces(front_id=front_id, province_id=plist):
        #         neighbours_data[p['province_id']] = p
        #
        # for neighbor_id, neighbor_data in neighbours_data.items():
        #     if clan_id in neighbor_data['attackers']:  # attack performed by land
        #         provinces[neighbor_id] = Province(neighbor_data, self.region)

        if provinces:
            start_time = min(set([i.prime_time for i in provinces.values()]))
        else:
            start_time = '12:00'
        hour, minute = re.match('(\d{2}):(\d{2})', start_time).groups()

        day_start = (datetime.now()-timedelta(hours=10)) \
            .replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        battle_matrix = OrderedDict()
        for i in range(16):
            battle_matrix[day_start + timedelta(minutes=30) * i] = []

        for time, battles_list in battle_matrix.items():
            for battle in provinces.values():
                if battle.has_battle_at(time):
                    battles_list.append(battle.at(time))

        context['battle_matrix'] = battle_matrix
        context['battle_matrix2'] = BattleMatrix(provinces)
        return context


class BattleMatrix(object):
    def __init__(self, provinces):
        self._provinces = provinces

    @property
    def times(self):
        res = []
        for i in self._provinces.values():
            res.extend(i.round_times().keys())
        return sorted(set(res))

    @property
    def table(self):
        table = defaultdict(lambda: [])
        for province_id, prov in self._provinces.items():
            for time in self.times:
                item_in_row = {
                    'class': '',
                    'url': '',
                    'text': '',
                }
                if prov.has_battle_at(time):
                    round_id = prov.round_times[time]
                    if round_id == 1:
                        text = 'Final'
                    elif round_id == 0:
                        text = 'Owner'
                    else:
                        text = "1/%s" % round_id
                    data = {
                        'class': 'btn-default',
                        'text': text,
                        'url': prov.url
                    }
                    try:
                        table[prov].append(data)
                    except KeyError:
                        table[prov].append('Unknown')
                else:
                    table[prov].append(item_in_row)

        return sorted(table.items(), key=lambda k: (k[0].server, k[0].province_id))
