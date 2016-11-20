import re
import os
import math
import pytz
from datetime import datetime, timedelta
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
from django.db.models import Count

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


class Province(object):
    def __init__(self, clan_id, province_dict):
        self._province = province_dict
        self._clan_id = clan_id

        self.province_id = self._province['province_id']
        self.arena_name = self._province['arena_name']
        self.province_name = self._province['province_name']
        self.prime_time = self._province['prime_time']
        self.prime_datetime = datetime.strptime(self._province['prime_time'], "%H:%M") \
            .replace(year=2016, second=0, microsecond=0)
        self.owner_clan = Clan.get_or_create(clan_id=self._province['owner_clan_id']) \
            if self._province['owner_clan_id'] else None

        self.server = self._province['server']

        # Parse time
        self._province['battles_start_at'] = \
            datetime.strptime(self._province['battles_start_at'], '%Y-%m-%dT%H:%M:%S')
        self.battle_date = self._province['battles_start_at'].date()

        for battle in self._province['active_battles']:
            battle['start_at'] = datetime.strptime(battle['start_at'], '%Y-%m-%dT%H:%M:%S')

    @property
    def tags(self):
        tags = ProvinceTag.objects.filter(date=self.battle_date, province_id=self.province_id)
        return ','.join([i.tag for i in tags])

    @property
    def bgcolor(self):
        return 'FFF' if self.prime_datetime.minute == 15 else '6F6'

    @property
    def rounds_count(self):
        if not self._province['landing_type']:
            return 0

        if self._province['landing_type'] == 'tournament':
            count = len(self._province['competitors']) + len(self._province['attackers'])
        else:
            count = len(self._province['attackers'])
        if count > 0:
            return int(math.ceil(math.log(count, 2)))
        return -1

    @property
    def round_times(self):
        times = {}
        for battle_time, value in self.battle_times.items():
            minute = 30 if battle_time.minute >= 30 else 0
            if 0 <= battle_time.minute < 15:
                minute = 0
            elif 15 <= battle_time.minute < 30:
                minute = 0
            elif 30 <= battle_time.minute < 45:
                minute = 30
            else:
                minute = 30

            times[battle_time.replace(minute=minute, second=0, microsecond=0)] = value
        return times

    def get_enemy_for_time(self, time):
        clan_id = self._clan_id
        for battle in self._province['active_battles']:
            if time <= battle['start_at'] < time + timedelta(minutes=30):
                if battle['clan_a']['clan_id'] == clan_id:
                    return Clan.get_or_create(clan_id=battle['clan_b']['clan_id'])
                if battle['clan_b']['clan_id'] == clan_id:
                    return Clan.get_or_create(clan_id=battle['clan_a']['clan_id'])
        return None

    @property
    def attack_type(self):
        if self._province['owner_clan_id'] == self._clan_id and (
            self._province['attackers'] or self._province['competitors']
        ):
            result = 'Defence'
        elif self._clan_id in self._province['attackers']:
            result = 'By land'
        elif self._clan_id in self._province['competitors']:
            result = 'Tournament'
        else:
            result = 'Unknown'
        return result

    @property
    def battle_times(self):
        rounds_count = self.rounds_count
        if rounds_count == -1:
            return {}

        battles_start_at = self._province['battles_start_at']
        if self._province['owner_clan_id'] == self._clan_id:
            times = {battles_start_at + timedelta(minutes=30) * rounds_count: 0}
        else:
            times = {}
            for i in range(rounds_count + 1):
                times[battles_start_at + timedelta(minutes=30) * i] = int(math.pow(2, rounds_count - i - 1))
        return times

    @property
    def url(self):
        return "https://ru.wargaming.net/globalmap" + self._province['uri']

    def has_battle_at(self, time):
        for bt in self.battle_times.keys():
            # 18:00:00 <= bt <= 18:29:59
            if time <= bt < time + timedelta(minutes=30):
                return True
        return False

    def at(self, time):
        res = self._province.copy()
        res['url'] = "https://ru.wargaming.net/globalmap" + res['uri']
        res['time'] = time
        return res

    def __repr__(self):
        return "<Battle for '%s' on '%s'>" % (self._province['province_id'], self._province['server'])


class ListBattles(TemplateView):
    template_name = 'list_battles.html'
    cached_time = None

    @staticmethod
    @retry(stop_max_attempt_number=5)
    def _clanprovinces(**kwargs):
        """wrapper to retry if WG servers has failed"""
        clan_id = kwargs['clan_id']
        path = 'cache/clan_provinces.json'
        if clan_id == 35039 and os.path.exists(path):
            with open(path) as f:
                clan_provinces = json.loads(f.read())
        else:
            clan_provinces = wot.globalmap.clanprovinces(**kwargs)
        return clan_provinces

    @retry(stop_max_attempt_number=5)
    def _provinces(self, **kwargs):
        """wrapper to retry if WG servers has failed"""
        clan_id = kwargs.pop('clan_id')
        path = 'cache/provinces-%s.json' % kwargs['front_id']
        if clan_id == 35039 and os.path.exists(path):
            self.cached_time = int((datetime.now() - datetime.fromtimestamp(os.stat(path).st_ctime)).total_seconds() / 60)
            with open(path) as f:
                provinces = json.load(f)
        else:
            provinces = wot.globalmap.provinces(**kwargs)
        return provinces

    @staticmethod
    @retry(stop_max_attempt_number=5)
    def _data(clan_id):
        """wrapper to retry if WG servers has failed"""
        path = 'cache/data.json'
        if clan_id == 35039 and os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            response = urllib2.urlopen('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan_id)
            data = json.loads(response.read())
        return data

    def get_context_data(self, **kwargs):
        context = super(ListBattles, self).get_context_data(**kwargs)
        clan_tag = self.request.GET.get('tag', 'SMIRK')
        clan = Clan.get_or_create(clan_tag=clan_tag)
        # clan_id = clan.id
        # province_list = defaultdict(lambda: [])  # list of all provinces we have any actions, by front
        # owned_provinces = []                     # list of all owned provinces
        # provinces_data = {}                      # provinces data
        # battle_matrix = OrderedDict()
        #
        # try:
        #     data = self._data(clan_id)
        # except:
        #     data = {'battles': [], 'planned_battles': []}
        #
        # # prepare list of provinces to query
        # for battle_type in ['battles', 'planned_battles']:
        #     for battle in data[battle_type]:
        #         province_list[battle['front_id']].append(battle['province_id'])
        #
        # # fetch for clan owned provinces
        # clan_provinces = self._clanprovinces(clan_id=clan_id, language='ru')[str(clan_id)]
        # if isinstance(clan_provinces, list):
        #     for own in clan_provinces:
        #         front_id = own['front_id']
        #         province_list[front_id].append(own['province_id'])
        #         owned_provinces.append(own['province_id'])
        #
        # # fetch for provinces data
        # for front_id in province_list.keys():
        #     plist = list(set(province_list[front_id]))  # make list unique
        #     for p in self._provinces(front_id=front_id, province_id=plist, clan_id=clan_id):
        #         provinces_data[p['province_id']] = p
        #
        # # **** Battle section *****
        # provinces = {}
        #
        # # fill battles from battles screen on GlobalMap
        # for battle_type in ['battles', 'planned_battles']:
        #     for battle in data[battle_type]:
        #         province_id = battle['province_id']
        #         provinces[province_id] = Province(clan_id, provinces_data[province_id])
        #
        # # fill defences from owned battles
        # for own in owned_provinces:
        #     if own not in provinces and (provinces_data[own]['attackers'] or provinces_data[own]['competitors']):
        #         provinces[own] = Province(clan_id, provinces_data[own])
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
        #     for p in self._provinces(front_id=front_id, province_id=plist, clan_id=clan_id):
        #         neighbours_data[p['province_id']] = p
        #
        # for neighbor, data in neighbours_data.items():
        #     if clan_id in data['attackers']:  # attack performed by land
        #         provinces[neighbor] = Province(clan_id, data)
        #
        # if provinces:
        #     start_time = min(set([i.prime_time for i in provinces.values()]))
        #     hour, minute = re.match('(\d{2}):(\d{2})', start_time).groups()
        #
        #     day_start = (datetime.now()-timedelta(hours=10)) \
        #         .replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        #     for i in range(16):
        #         battle_matrix[day_start + timedelta(minutes=30) * i] = []
        #
        #     for time, battles_list in battle_matrix.items():
        #         for battle in provinces.values():
        #             if battle.has_battle_at(time):
        #                 battles_list.append(battle.at(time))
        #
        # context['battle_matrix'] = battle_matrix
        # context['battle_matrix2'] = BattleMatrix(provinces)
        context['attacks'], context['all_times'], context['battle_matrix3'] = table2()
        # context['cached_time'] = self.cached_time
        return context


class BattleMatrix(object):
    def __init__(self, provinces):
        self._provinces = provinces

    @property
    def times(self):
        res = []
        # print self._provinces
        for i in self._provinces.values():
            res.extend(i.round_times.keys())
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
                        'url': prov.url,
                        'enemy': prov.get_enemy_for_time(time),
                    }
                    if text == 'Owner':
                        data['enemy'] = prov.owner_clan
                    try:
                        table[prov].append(data)
                    except KeyError:
                        table[prov].append('Unknown')
                else:
                    table[prov].append(item_in_row)

        return sorted(table.items(), key=lambda k: (k[0].prime_datetime.minute == 15, k[0].server, k[0].province_id))


def table2():
    # TODO: possible bug if battles after 3 AM MSK time
    today = datetime.now(tz=pytz.UTC)

    clan = Clan.objects.get(pk=35039)
    attacks = ProvinceAssault.objects.annotate(clans_count=Count('clans')).filter(
        clans_count__gt=0, clans=clan, date__gte=today.date())

    min_time = today.replace(second=0, microsecond=0) - timedelta(minutes=today.minute % 30)
    table = []  # [attacks, {time: battle, time: battle, ...}]

    all_times = []
    # for attack in attacks:
    #         table.append([attack, attack.planned_times])
    #         all_times.extend(attack.planned_times.keys())

    all_times = [time for time in all_times]
    all_times = sorted(list(set(all_times)))

    return attacks, all_times, table


class ListBattlesJson(View):
    def get(self, *args, **kwargs):
        # dt = datetime.now().replace(second=0, microsecond=0, tzinfo=pytz.UTC)
        #
        # battles = OrderedDict([
        #     ('province', [(dt.replace(hour=13, minute=30) + timedelta(minutes=30)*i).isoformat() for i in range(6)]),
        #     ('province2', [(dt.replace(hour=12, minute=30) + timedelta(minutes=30)*i).isoformat() for i in range(6)]),
        #     ('province3', [(dt.replace(hour=16, minute=30) + timedelta(minutes=30)*i).isoformat() for i in range(6)]),
        # ])

        # assault.as_clan_json(clan)

        # {
        #   'time_range': [ '2016-10-11T22:00:00', '2016-11-11T19:00:00'],
        #   'assaults': [{
        #     'province_info': {province_data},
        #     'clans': [{clan_info}, ...],
        #     'battles': [{battle_info}, {...}, .... ],
        #   }, ... ],
        # }

        clan = Clan.objects.get(pk=35039)
        assaults = ProvinceAssault.objects.filter(date=datetime.now().date(), clans=clan)

        times = []
        for assault in assaults:
            times.extend(assault.planned_times)

        assaults = [assault.as_clan_json(clan) for assault in assaults]

        return JsonResponse({
            'time_range': [min(times), max(times)],
            'assaults': sorted(
                assaults,
                key=lambda v: (v['province_info']['prime_time'].minute == 15, v['province_info']['prime_time'])
            ),
        })
