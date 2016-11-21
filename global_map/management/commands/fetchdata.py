from django.conf import settings
from datetime import datetime, timedelta, time
import pytz
from django.core.management.base import BaseCommand, CommandError

from django.db.models import Q
import requests
import wargaming
import logging

from wargaming.exceptions import RequestError

from global_map.models import Front, Clan, Province, ProvinceAssault, ProvinceBattle, ClanArenaStat

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
logger = logging.getLogger(__name__)


def update_province(front_id, province_data):
    p = province_data
    province_owner = p['owner_clan_id'] and Clan.objects.get_or_create(pk=p['owner_clan_id'])[0]
    front = Front.objects.get(front_id=front_id)
    province = Province.objects.update_or_create(front=front, province_id=p['province_id'], defaults={
        'province_name': p['province_name'],
        'province_owner': province_owner,
        'arena_id': p['arena_id'],
        'arena_name': p['arena_name'],
        'server': p['server'],
        'prime_time': time(*map(int, p['prime_time'].split(':'))),  # UTC time
    })[0]

    clans = set([
        Clan.objects.get_or_create(pk=clan_id)[0]
        for clan_id in p['competitors'] + p['attackers']
    ])

    if clans:
        dt = datetime.strptime(p['battles_start_at'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC)
        prime_dt = dt.replace(hour=province.prime_time.hour, minute=province.prime_time.minute)

        # if battle starts next day, but belongs to previous
        date = dt.date() if dt >= prime_dt else (dt - timedelta(days=1)).date()

        assault = ProvinceAssault.objects.update_or_create(province=province, date=date, defaults={
            'current_owner': province_owner,
            'prime_time': province.prime_time,
            'arena_id': province.arena_id,
            'landing_type': p['landing_type'],
            'round_number': p['round_number'],
        })[0]
        if set(assault.clans.all()) != clans:
            assault.clans.clear()
            assault.clans.add(*clans)

        for active_battle in p['active_battles']:
            ProvinceBattle.objects.get_or_create(
                assault=assault,
                province=province,
                arena_id=p['arena_id'],
                clan_a=Clan.objects.get_or_create(pk=active_battle['clan_a']['clan_id'])[0],
                clan_b=Clan.objects.get_or_create(pk=active_battle['clan_b']['clan_id'])[0],
                start_at=datetime.strptime(active_battle['start_at'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC),
                round=active_battle['round'],
            )


class ProvinceInfo(dict):
    def __init__(self, province_id, seq=None, **kwargs):
        super(ProvinceInfo, self).__init__(self, seq=seq, **kwargs)
        resp = requests.get('https://ru.wargaming.net/globalmap/game_api/province_info?alias=%s' % province_id).json()
        self.update({
            # 'arena_id', => NO INFO
            'arena_name': resp['province']['arena_name'],
            # 'attackers', == > tournament_info
            # 'battles_start_at', NO INFO
            # 'landing_type', NO INFO
            'neighbours': [i['alias'] for i in resp['province']['neighbours']],
            'owner_clan_id': resp['owner']['id'],
            'prime_time': resp['province']['primetime'],
            'province_id': province_id,
            'province_name': resp['province']['name'],
            'round_number': resp['province']['turns_till_primetime'],
            'server': resp['province']['periphery'],
            # 'status': resp['province']['type'],  NO INFO
            'uri': '/#province/%s' % province_id,
            # 'active_battles': resp['province'][''],  ==> tournament_info
        })


class TournamentInfo(dict):
    def __init__(self, province_id, seq=None, **kwargs):
        super(TournamentInfo, self).__init__(seq=None, **kwargs)
        self.update(requests.get(
            'https://ru.wargaming.net/globalmap/game_api/tournament_info?alias=%s' % province_id).json())

    def clans_info(self):
        clans = {}
        for battle in self['battles']:
            clans[battle['first_competitor']['id']] = battle['first_competitor']
            clans[battle['second_competitor']['id']] = battle['second_competitor']
        for clan in self['pretenders'] or []:
            clans[clan['id']] = clan
        return clans


def update_clan(clan_id):
    clan = Clan.objects.get_or_create(pk=clan_id)[0]
    province_ids = {}
    fronts = {}
    # fill fronts info
    try:
        for front in wot.globalmap.fronts():
            fronts[front['front_id']] = Front.objects.update_or_create(front_id=front['front_id'], defaults={
                'max_vehicle_level': front['max_vehicle_level'],
            })[0]
    except RequestError as e:
        logger.error("Import error wot.globalmap.fronts returned %s (%s), fallback to DB records",
                     e.code, e.message)

    # poll unofficial WG API
    resp = requests.get('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan_id)
    data = resp.json()
    for p in data['battles'] + data['planned_battles']:
        province_ids.setdefault(p['front_id'], []).append(p['province_id'])

    # fetch clan battles
    try:
        clan_provinces = wot.globalmap.clanprovinces(clan_id=clan_id, language='ru')
        if clan_provinces:
            for p in clan_provinces[str(clan_id)]:
                province_ids.setdefault(p['front_id'], []).append(p['province_id'])
    except RequestError as e:
        logger.error("Import error wot.globalmap.clanprovinces returned %s (%s)",
                     e.code, e.message)

    # fetch existing battles
    existing_assaults = {}
    for pa in ProvinceAssault.objects.filter(clans=clan, date=datetime.now(tz=pytz.UTC).date()):
        existing_assaults[pa.province.province_id] = pa
        province_ids.setdefault(pa.province.front_id, []).append(pa.province.province_id)

    # split provinces by 100
    for front_id, provinces in province_ids.items():
        province_ids[front_id] = [provinces[i:i+100] for i in range(0, len(provinces), 100)]

    # fetch all provinces and store records to DB
    clans = []
    for front_id, provinces_sets in province_ids.items():
        for provinces_set in provinces_sets:
            try:
                provinces = wot.globalmap.provinces(
                    front_id=front_id, province_id=','.join(provinces_set))  # , fields=','.join([
                #         'arena_id',
                #         'arena_name',
                #         'attackers',
                #         'battles_start_at',
                #         'competitors'
                #         'landing_type',
                #         'neighbours',
                #         'owner_clan_id',
                #         'prime_time',
                #         'province_id',
                #         'province_name',
                #         'round_number',
                #         'server',
                #         'status',
                #         'uri',
                #         'active_battles',
                # ]))

                # On success clear clans in ProvinceAssault
                for p in provinces_set:
                    if p in existing_assaults:
                        existing_assaults[p].clans.clear()
            except RequestError as e:
                logger.error("Import error wot.globalmap.provinces returned %s (%s), skip",
                             e.code, e.message)
            else:
                for province_data in provinces:
                    update_province(front_id, province_data)  # update DB
                    clans.extend(province_data['attackers'])
                    clans.extend(province_data['competitors'])
                    if province_data['owner_clan_id']:
                        clans.append(province_data['owner_clan_id'])

    clans = list(set(clans))
    for clans_set in [clans[i:i+10] for i in range(0, len(clans), 10)]:
        for clan_id, info in wot.globalmap.claninfo(clan_id=clans_set).items():
            Clan.objects.update_or_create(pk=clan_id, defaults={
                'tag': info['tag'],
                'title': info['name'],
                'elo_6': info['ratings']['elo_6'],
                'elo_8': info['ratings']['elo_8'],
                'elo_10': info['ratings']['elo_10'],
            })

    # Update clan stats from unofficial API clans WR on maps
    for pa in ProvinceAssault.objects.filter(clans=clan, date=datetime.now(tz=pytz.UTC).date()):
        ti = TournamentInfo(pa.province.province_id)
        for clan_id, info in ti.clans_info().items():
            ClanArenaStat.objects.update_or_create(clan_id=clan_id, arena_id=pa.province.arena_id, defaults={
                'wins_percent': info['arena_wins_percent'],
                'battles_count': info['arena_battles_count'],
            })
        ClanArenaStat.objects.update_or_create(clan_id=ti['owner']['id'], arena_id=pa.province.arena_id, defaults={
            'wins_percent': ti['owner']['arena_wins_percent'],
            'battles_count': ti['owner']['arena_battles_count'],
        })


class Command(BaseCommand):
    help = 'Save map to cache'

    def handle(self, *args, **options):
        clan_id = 35039  # SMIRK
        update_clan(clan_id)
