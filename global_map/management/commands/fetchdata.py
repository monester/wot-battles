# coding=utf-8
from django.conf import settings
from django.db.models import Q
from datetime import datetime, timedelta, time
import pytz
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import mail_admins

from collections import defaultdict
import json
import requests
import wargaming
import logging

from wargaming.exceptions import RequestError

from global_map.models import Front, Clan, Province, ProvinceAssault, ProvinceBattle, ClanArenaStat

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
logger = logging.getLogger(__name__)

day_begin_time = time(3, 0)  # battle day starts at 06:00 MSK(UTC+3)


def utc_now():
    return datetime.now(tz=pytz.UTC)


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


def update_province(province, province_data):
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
    status = province_data['status']

    battles_start_at = datetime.strptime(province_data['battles_start_at'], '%Y-%m-%dT%H:%M:%S') \
        .replace(tzinfo=pytz.UTC)

    logger.debug("update_province: running update for province '%s'", province_id)

    province.province_name = province_name
    province.province_owner = province_owner
    province.arena_id = arena_id
    province.arena_name = arena_name
    province.server = server
    province.prime_time = time(*map(int, prime_time.split(':')))  # UTC time
    province.save()

    clans = {
        clan_id: Clan.objects.get_or_create(pk=clan_id)[0]
        for clan_id in competitors + attackers
    }

    if status == 'STARTED' and not clans:
        # BUG in WG API: it returns empty list in 'competitors' or 'attackers'
        # could happen after start of prime time
        for active_battle in active_battles:
            clan_a_id = active_battle['clan_a']['clan_id']
            clan_b_id = active_battle['clan_b']['clan_id']
            clans[clan_a_id] = Clan.objects.get_or_create(pk=clan_a_id)[0]
            clans[clan_b_id] = Clan.objects.get_or_create(pk=clan_b_id)[0]
        for clan in province.tournament_info.pretenders:
            clans[clan['id']] = Clan.objects.get_or_create(pk=clan['id'])[0]

    dt = battles_start_at
    today_start = battles_start_at.replace(
        hour=day_begin_time.hour,
        minute=day_begin_time.minute,
        second=day_begin_time.second,
        microsecond=day_begin_time.microsecond
    )

    # if battle starts next day, but belongs to previous
    date = dt.date() if dt >= today_start else (dt - timedelta(days=1)).date()
    try:
        assault = ProvinceAssault.objects.get(province=province, date=date)
    except ProvinceAssault.DoesNotExist:
        assault = None

    if clans or assault:
        if not assault:
            assault = ProvinceAssault.objects.create(
                province=province,
                date=date,
                current_owner=province_owner,
                prime_time=province.prime_time,
                arena_id=province.arena_id,
                landing_type=landing_type,
                round_number=round_number,
                status=status,
            )
            logger.debug("created assault for '%s' {current_owner: '%s', date: '%s', 'attackers_count': %s}",
                         province_id, province.province_owner, date, len(province_data['attackers']))
        else:
            assault.current_owner = province_owner
            assault.prime_time = province.prime_time
            assault.arena_id = province.arena_id
            assault.landing_type = landing_type
            assault.round_number = round_number
            assault.status = status
            assault.save()

        # cleanup: check for previous Assaults
        ProvinceAssault.objects \
            .filter(province=province, status='STARTED') \
            .exclude(pk=assault.pk) \
            .update(status='FINISHED')

        # TODO: remove this code
        if status == 'FINISHED' and battles_start_at > assault.datetime:
            # NEVER SHOULD HAPPEN
            mail_admins('Update finished Assault for %s' % province_id,
                        json.dumps(province_data, sort_keys=True, indent=4))
            logger.error("Status FINISHED for province attack on running assault, do not update assault")
            return

        for active_battle in active_battles:
            # WG return different time for same battle, that is why start_at
            # can be updated.
            clan_a_id = active_battle['clan_a']['clan_id']
            clan_b_id = active_battle['clan_b']['clan_id']
            clan_a = clans[clan_a_id] if clan_a_id in clans else Clan.objects.get_or_create(pk=clan_a_id)[0]
            clan_b = clans[clan_b_id] if clan_b_id in clans else Clan.objects.get_or_create(pk=clan_b_id)[0]

            pb, created = ProvinceBattle.objects.update_or_create(
                assault=assault,
                province=province,
                arena_id=arena_id,
                clan_a=clan_a,
                clan_b=clan_b,
                round=active_battle['round'],
                defaults={
                    'start_at': datetime.strptime(
                        active_battle['start_at'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC)
                }
            )
            if created:
                logger.debug("created battle for '%s' {round: '%s', clan_a: '%s', clan_b '%s'}",
                             province_id, pb.round, repr(pb.clan_a), repr(pb.clan_b))

        # if owner in attackers/competitors list
        # it can happen if we're filling assaulting clans from battles
        if assault.current_owner and assault.current_owner.id in clans:
            del clans[assault.current_owner.id]

        if set(assault.clans.all()) != set(clans.values()):
            assault.clans.clear()
            if clans:
                assault.clans.add(*clans.values())
                logger.debug("add clans to province '%s': %s",
                             province_id, ' '.join([repr(c) for c in clans.values()]))
            else:
                logger.debug("no more clans assaulting province '%s', cleared clans", province_id)
                if assault.datetime > utc_now():
                    logger.debug("update_province: removed assault for province %s", province_id)
                    assault.delete()
                else:
                    logger.warn("no clans left in assault %s after its prime time", province_id)


def collect_clan_related_provinces(clan):
    provinces = []

    # fetch clan battles
    try:
        clan_provinces = wot.globalmap.clanprovinces(clan_id=clan.id, language='ru')[str(clan.id)]
        if clan_provinces:
            for p in clan_provinces:
                provinces.append(Province.objects.get_or_create(
                    province_id=p['province_id'], front=Front.objects.get(front_id=p['front_id']))[0])
    except RequestError as e:
        logger.error("Import error wot.globalmap.clanprovinces returned %s (%s)",
                     e.code, e.message)

    # poll unofficial WG API
    data = requests.get('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan.id).json()
    for p in data['battles'] + data['planned_battles']:
        provinces.append(Province.objects.get_or_create(
                    province_id=p['province_id'], front=Front.objects.get(front_id=p['front_id']))[0])

    # fetch existing ProvinceAssault
    now = datetime.now(tz=pytz.UTC)
    for pa in ProvinceAssault.objects.order_by('province', '-date').distinct('province'):
        if clan in pa.clans.all() or pa.current_owner == clan:
            if pa.datetime >= now:  # battle is planned
                provinces.append(pa.province)
            elif pa.datetime + timedelta(hours=6) >= now:  # battle is running
                provinces.append(pa.province)

    return list(set(provinces))


def get_provinces_data(provinces):
    provinces_data = {}
    map_id_model = {}
    fronts = defaultdict(list)

    # map province_id to province model
    for province in provinces:
        map_id_model[province.province_id] = province

    # group by front_id
    for province in provinces:
        fronts[province.front.front_id].append(str(province.province_id))

    # fetch data
    for front_id, front_provinces in fronts.items():
        province_ids = [','.join(front_provinces[i:i+100]) for i in range(0, len(front_provinces), 100)]
        for province_id in province_ids:
            try:
                result_list = wot.globalmap.provinces(front_id=front_id, province_id=province_id)
            except RequestError as e:
                logger.error("Import error wot.globalmap.provinces returned %s (%s), skip", e.code, e.message)
            else:
                for data in result_list:
                    province_id = data['province_id']
                    provinces_data[map_id_model[province_id]] = data

    return provinces_data


def update_winners_from_log(clan):
    resp = requests.get('https://ru.wargaming.net/globalmap/game_api/clan/%s/log?'
                        'category=battles&page_number=1&page_size=3000' % clan.id).json()['data']

    logs = defaultdict(list)
    battle_result_types = [
        'SUPER_FINAL_BATTLE_LOST',
        'SUPER_FINAL_BATTLE_WON',
        'TOURNAMENT_BATTLE_FINISHED_WITH_DRAW',
        'TOURNAMENT_BATTLE_LOST',
        'TOURNAMENT_BATTLE_WON',
    ]
    for log in resp:
        if log['type'] in battle_result_types:
            province_id = log['target_province']['alias']
            log['created_at'] = datetime.strptime(log['created_at'][0:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.UTC)
            log['enemy_clan'] = Clan.objects.get_or_create(pk=log['enemy_clan']['id'])[0]
            logs[province_id].insert(0, log)

    province_battles = defaultdict(list)
    for pb in ProvinceBattle.objects.filter(winner=None).filter(Q(clan_a=clan) | Q(clan_b=clan)).order_by('start_at') \
            .select_related('province'):
        province_battles[pb.province.province_id].append(pb)

    for province_id in province_battles.keys():
        pb_index = log_index = 0
        total_pb = len(province_battles[province_id])
        total_logs = len(logs[province_id])
        while True:
            if pb_index >= total_pb or log_index >= total_logs:
                break

            pb = province_battles[province_id][pb_index]
            log = logs[province_id][log_index]

            start_at = pb.start_at
            result_at = log['created_at']

            if start_at > result_at:  # result earlier than battle started
                log_index += 1
                continue
            # match if -5 ... 20 from battle start time
            # for example if battle starts at 17:00 it would be matched by result 16:55 ... 17:20
            if result_at + timedelta(minutes=5) >= start_at >= result_at - timedelta(minutes=20):
                pb.winner = Clan.objects.get_or_create(pk=log['winner_id'])[0]
                pb.save()
                pb_index += 1
                log_index += 1
                continue
            if result_at > start_at + timedelta(minutes=20):
                pb_index += 1


def update_clan(clan_id):
    clan = Clan.objects.get_or_create(pk=clan_id)[0]
    province_ids = {}
    fronts = {}

    # check global map status
    globalmap_info = wot.globalmap.info()
    if globalmap_info['state'] == 'frozen':
        logger.info("Map is frozen, skipping update")
        return

    # fill fronts info
    try:
        for front in wot.globalmap.fronts():
            fronts[front['front_id']] = Front.objects.update_or_create(front_id=front['front_id'], defaults={
                'max_vehicle_level': front['max_vehicle_level'],
            })[0]
    except RequestError as e:
        logger.error("Import error wot.globalmap.fronts returned %s (%s), fallback to DB records",
                     e.code, e.message)

    # split provinces by 100
    for front_id, provinces in province_ids.items():
        province_ids[front_id] = [provinces[i:i+100] for i in range(0, len(provinces), 100)]

    # Get list of all provinces belonging to clan: defence or attack
    provinces_list = collect_clan_related_provinces(clan)
    logger.info('Clan %s related provinces: %s', repr(clan), json.dumps(map(str, provinces_list)))

    # fetch all provinces data
    provinces_data = get_provinces_data(provinces_list)

    for province, data in provinces_data.items():
        update_province(province, data)

    update_winners_from_log(clan)


class Command(BaseCommand):
    help = 'Save map to cache'

    def add_arguments(self, parser):
        parser.add_argument('clan_id', nargs='*', type=int)

    def handle(self, *args, **options):
        from time import time
        start = time()
        logger.info("Starting import at %s" % datetime.now(tz=pytz.UTC))
        for clan_id in options['clan_id'] or [35039]:
            try:
                update_clan(clan_id)
            except Exception:
                logger.critical("Unknown error", exc_info=True)
        logger.info("Finished import at %s, seconds elapsed %s",
                    datetime.now(tz=pytz.UTC), time() - start)
