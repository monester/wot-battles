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


def update_province(front_id, assault, province_data):
    province_id = province_data['province_id']
    province_name = province_data['province_name']
    province_owner = province_data['owner_clan_id'] and \
                     Clan.objects.get_or_create(pk=province_data['owner_clan_id'])[0]
    arena_id = province_data['arena_id']
    arena_name = province_data['arena_name']
    server = province_data['server']
    prime_time = province_data['prime_time']
    competitors = province_data['competitors']
    attackers = province_data['attackers']
    landing_type = province_data['landing_type']
    round_number = province_data['round_number']
    active_battles = province_data['active_battles']

    battles_start_at = datetime.strptime(province_data['battles_start_at'], '%Y-%m-%dT%H:%M:%S') \
        .replace(tzinfo=pytz.UTC)

    front = Front.objects.get(front_id=front_id)
    logger.debug("update_province: running update for province '%s'", province_id)
    province = Province.objects.update_or_create(front=front, province_id=province_id, defaults={
        'province_name': province_name,
        'province_owner': province_owner,
        'arena_id': arena_id,
        'arena_name': arena_name,
        'server': server,
        'prime_time': time(*map(int, prime_time.split(':'))),  # UTC time
    })[0]

    clans = set([
        Clan.objects.get_or_create(pk=clan_id)[0]
        for clan_id in competitors + attackers
    ])

    dt = battles_start_at
    prime_dt = dt.replace(hour=province.prime_time.hour, minute=province.prime_time.minute)

    # if battle starts next day, but belongs to previous
    date = dt.date() if dt >= prime_dt else (dt - timedelta(days=1)).date()

    if assault or clans:
        if assault:
            assault.current_owner = province_owner
            assault.prime_time = province.prime_time
            assault.arena_id = province.arena_id
            assault.landing_type = landing_type
            assault.round_number = round_number
            assault.save()
        else:
            assault = ProvinceAssault.objects.create(
                province=province,
                date=date,
                current_owner=province_owner,
                prime_time=province.prime_time,
                arena_id=province.arena_id,
                landing_type=landing_type,
                round_number=round_number,
            )
            logger.debug("update_province: created assault for '%s' {current_owner: '%s', date: '%s'}",
                         province_id, province.province_owner, date)

        for active_battle in active_battles:
            created, pb = ProvinceBattle.objects.get_or_create(
                assault=assault,
                province=province,
                arena_id=arena_id,
                clan_a=Clan.objects.get_or_create(pk=active_battle['clan_a']['clan_id'])[0],
                clan_b=Clan.objects.get_or_create(pk=active_battle['clan_b']['clan_id'])[0],
                start_at=datetime.strptime(active_battle['start_at'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC),
                round=active_battle['round'],
            )
            if created:
                logger.debug("update_province: created battle for '%s' {round: '%s', clan_a: '%s', clan_b '%s'}",
                             province_id, pb.round, repr(pb.clan_a), repr(pb.clan_b))

        if set(assault.clans.all()) != clans:
            if clans:
                assault.clans.clear()
                assault.clans.add(*clans)
                logger.debug("update_province: add clans to province '%s': %s",
                             province_id, ' '.join([repr(c) for c in clans]))
            else:
                assault.clans.clear()
                logger.debug("update_province: no more clans assaulting province '%s', cleared clans", province_id)
                if assault.datetime > datetime.now(tz=pytz.UTC):
                    logger.debug("update_province: removed assault for province %s", province_id)
                    assault.delete()
                else:
                    logger.warn("update_province: no clans left in assault %s but it is running", province_id)


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
            if 'first_competitor' in battle and battle['first_competitor']:
                clans[battle['first_competitor']['id']] = battle['first_competitor']
            if 'second_competitor' in battle and battle['second_competitor']:
                clans[battle['second_competitor']['id']] = battle['second_competitor']
        for clan in self['pretenders'] or []:
            clans[clan['id']] = clan
        return clans


def update_clan(clan_id):
    clan = Clan.objects.get_or_create(pk=clan_id)[0]
    province_ids = {}
    fronts = {}

    # check global map status
    globalmap_info = wot.globalmap.info()
    if globalmap_info['state'] == 'frozen':
        logger.info("Map is frozen, skipping update")
        # return

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
        province_ids.setdefault(p['front_id'], []).append((p['province_id'], None))

    # fetch clan battles
    try:
        clan_provinces = wot.globalmap.clanprovinces(clan_id=clan_id, language='ru')
        if clan_provinces:
            for p in clan_provinces[str(clan_id)]:
                province_ids.setdefault(p['front_id'], []).append((p['province_id'], None))
    except RequestError as e:
        logger.error("Import error wot.globalmap.clanprovinces returned %s (%s)",
                     e.code, e.message)

    # fetch existing battles
    existing_assaults = {}
    for pa in ProvinceAssault.objects.filter(date=datetime.now(tz=pytz.UTC).date()) \
            .filter(Q(clans=clan) | Q(current_owner=clan)):
        existing_assaults[pa.province.province_id] = pa
        province_ids.setdefault(pa.province.front.front_id, []).append((pa.province.province_id, pa))

    # split provinces by 100
    for front_id, provinces in province_ids.items():
        province_ids[front_id] = [provinces[i:i+100] for i in range(0, len(provinces), 100)]

    # fetch all provinces and store records to DB
    clans = []
    for front_id, provinces_sets in province_ids.items():
        for provinces_set in provinces_sets:
            province_set = dict(provinces_set)
            try:
                provinces = wot.globalmap.provinces(front_id=front_id, province_id=','.join(province_set.keys()))
            except RequestError as e:
                logger.error("Import error wot.globalmap.provinces returned %s (%s), skip", e.code, e.message)
            else:
                for province_data in provinces:
                    update_province(front_id, province_set[province_data['province_id']], province_data)  # update DB
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
        from time import time
        start = time()
        logger.info("Starting import at %s" % datetime.now(tz=pytz.UTC))
        clan_id = 35039  # SMIRK
        try:
            update_clan(clan_id)
        except Exception:
            logger.critical("Unknown error", exc_info=True)
        logger.info("Finished import at %s, seconds elapsed %s",
                    datetime.now(tz=pytz.UTC), time()-start)
