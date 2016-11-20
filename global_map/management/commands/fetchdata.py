from django.conf import settings
from datetime import datetime, timedelta, time
import pytz
from django.core.management.base import BaseCommand, CommandError

from django.db.models import Q
import requests
import wargaming

from global_map.models import Front, Clan, Province, ProvinceAssault, ProvinceBattle

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')


def update_province(front_id, province_data):
    p = province_data
    province_owner = p['owner_clan_id'] and Clan.objects.get_or_create(pk=p['owner_clan_id'])[0]
    province = Province.objects.update_or_create(front_id=front_id, province_id=p['province_id'], defaults={
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


def update_clan(clan_id):
    clan = Clan.objects.get(pk=clan_id)
    province_ids = {}
    # fill fronts info
    for front in wot.globalmap.fronts():
        Front.objects.update_or_create(front_id=front['front_id'], defaults={
            'max_vehicle_level': front['max_vehicle_level'],
        })

    # poll unofficial WG API
    resp = requests.get('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan_id)
    data = resp.json()
    for p in data['battles'] + data['planned_battles']:
        province_ids.setdefault(p['front_id'], []).append(p['province_id'])

    # fetch clan battles
    clan_provinces = wot.globalmap.clanprovinces(clan_id=clan_id, language='ru')
    if clan_provinces:
        for p in clan_provinces[str(clan_id)]:
            province_ids.setdefault(p['front_id'], []).append(p['province_id'])

    # fetch existing battles
    for p in ProvinceAssault.objects.filter(clans=clan, date=datetime.now(tz=pytz.UTC).date()):
        province_ids.setdefault(p.province.front_id, []).append(p.province.province_id)

    # split provinces by 100
    for front_id, provinces in province_ids.items():
        province_ids[front_id] = [provinces[i:i+100] for i in range(0, len(provinces), 100)]

    # fetch all provinces and store records to DB
    clans = []
    for front_id, provinces_set in province_ids.items():
        for provinces in provinces_set:
            provinces = wot.globalmap.provinces(front_id=front_id, province_id=','.join(provinces))
            for province_data in provinces:
                update_province(front_id, province_data)  # update DB
                clans.extend(province_data['attackers'])
                clans.extend(province_data['competitors'])
                if province_data['owner_clan_id']:
                    clans.append(province_data['owner_clan_id'])

    clans = list(set(clans))
    for clans_set in [clans[i:i+10] for i in range(0, len(clans), 10)]:
        for clan_id, clan in wot.globalmap.claninfo(clan_id=clans_set).items():
            Clan.objects.update_or_create(pk=clan_id, defaults={
                'tag': clan['tag'],
                'title': clan['name'],
                'elo_6': clan['ratings']['elo_6'],
                'elo_8': clan['ratings']['elo_8'],
                'elo_10': clan['ratings']['elo_10'],
            })


class Command(BaseCommand):
    help = 'Save map to cache'

    def handle(self, *args, **options):
        clan_id = 35039  # SMIRK
        update_clan(clan_id)
