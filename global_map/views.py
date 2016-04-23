# Create your views here.
import pytz
import math
from datetime import datetime, timedelta
import json
from django.views.generic import TemplateView
from models import Clan
import urllib2
from collections import OrderedDict

import wargaming
# WARGAMING_KEY = '2f9b826b353eb63d993d6f0d1653c5ff' # server
WARGAMING_KEY = '540da2676c01efaee6c4c59c7a0f0f52' # mobile
wot = wargaming.WoT(WARGAMING_KEY, base_url='https://api.worldoftanks.ru/wot/')
wgn = wargaming.WGN(WARGAMING_KEY, base_url='https://api.worldoftanks.ru/wgn/')


class Battle(object):
    def __init__(self, clan_id, battle_dict, province_dict):
        self._battle = battle_dict
        self._province = province_dict
        self._clan_id = clan_id

        # Parse time
        self._province['battles_start_at'] = \
            datetime.strptime(self._province['battles_start_at'], '%Y-%m-%dT%H:%M:%S')

    @property
    def rounds_count(self):
        if not self._province['landing_type']:
            return 0

        if self._province['landing_type'] == 'tournament':
            count = len(self._province['competitors'])
        else:
            count = len(self._province['attackers'])
        if count > 0:
            return int(math.ceil(math.log(count, 2)))
        return -1

    @property
    def battle_times(self):
        rounds_count = self.rounds_count
        if rounds_count == -1:
            return []

        battles_start_at = self._province['battles_start_at']
        if self._province['owner_clan_id'] == self._clan_id:
            times = [battles_start_at + timedelta(minutes=30) * rounds_count]
        else:
            times = []
            for i in range(rounds_count + 1):
                times.append(battles_start_at + timedelta(minutes=30) * i)
        return times

    def has_battle_at(self, time):
        for bt in self.battle_times:
            # 18:00:00 <= bt <= 18:29:59
            if time <= bt < time + timedelta(minutes=30):
                return True
        return False

    def at(self, time):
        res = self._province.copy()
        res['url'] = "https://ru.wargaming.net/globalmap" + res['uri']
        res['time'] = time  # TODO: replace with actual time
        return res

    def __repr__(self):
        return "<Battle for '%s' on '%s'>" % (self._province['province_id'], self._province['server'])


class ListBattles(TemplateView):
    template_name = 'list_battles.html'

    def get_context_data(self, **kwargs):
        context = super(ListBattles, self).get_context_data(**kwargs)
        clan_tag = self.request.GET.get('tag', 'SMIRK')
        clan = Clan.get_or_create(clan_tag=clan_tag)
        clan_id = clan.id

        response = urllib2.urlopen('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan_id)
        data = json.loads(response.read())

        province_list = [battle['province_id']
                         for battle_type in ['battles', 'planned_battles']
                         for battle in data[battle_type]]

        owned_provinces = []
        for own in wot.globalmap.clanprovinces(clan_id=clan_id, language='ru')[str(clan_id)]:
            province_list.append(own['province_id'])
            owned_provinces.append(own['province_id'])

        provinces = {p['province_id']: p
            for p in wot.globalmap.provinces(front_id='1604_ru_event_west', language='ru', province_id=province_list)
        }

        battles = {}
        for battle_type in ['battles', 'planned_battles']:
            for battle in data[battle_type]:
                battles[battle['province_id']] = Battle(clan_id, battle, provinces[battle['province_id']])

        for own in owned_provinces:
            if own not in battles:
                battles[own] = Battle(clan_id, None, provinces[own])

        for battle_type in ['battles', 'planned_battles']:
            context[battle_type] = data[battle_type]
            for battle in context[battle_type]:
                battle['battle_time'] = datetime.strptime(battle['battle_time'][0:19], '%Y-%m-%d %H:%M:%S')
                battle['province'] = province = provinces[battle['province_id']]

                competitors = battle['province']['competitors']
                attackers = battle['province']['attackers']
                battle['sum_ca'] = sum_ca = len(competitors) + len(attackers)
                if sum_ca > 0:
                    round_count = int(math.ceil(math.log(sum_ca, 2)))
                else:
                    round_count = 0
                battle['type'] = 'Attack' if battle['province']['owner_clan_id'] != clan_id else 'Defence'
                if battle['type'] == 'Defence':
                    if province['status'] == 'STARTED':
                        battle['expected_battle'] = battle['battle_time']
                    else:
                        battle['expected_battle'] = battle['battle_time'] + timedelta(minutes=30) * round_count

        # for battle in context['battles']:
        #     if battle['battle_time'] - datetime.now() < timedelta(minutes=30):
        #         battle['style'] = 'success'
        #
        # for battle in context['battles']:
        #     if battle['battle_time'] - datetime.now() < timedelta(minutes=30):
        #         battle['style'] = 'success'

        day_start = (datetime.now()-timedelta(hours=10)).replace(hour=16, minute=0, second=0, microsecond=0)
        battle_matrix = OrderedDict()
        for i in range(16):
            battle_matrix[day_start + timedelta(minutes=30) * i] = []

        for time, battles_list in battle_matrix.items():
            for battle in battles.values():
                if battle.has_battle_at(time):
                    battles_list.append(battle.at(time))

        context['battle_matrix'] = battle_matrix
        return context
