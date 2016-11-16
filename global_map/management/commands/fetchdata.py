from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import json
import requests
import wargaming

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')


class Command(BaseCommand):
    help = 'Save map to cache'

    def handle(self, *args, **options):
        clan_id = 35039

        province_ids = {}
        try:
            # cache unofficial WG API
            resp = requests.get('https://ru.wargaming.net/globalmap/game_api/clan/%s/battles' % clan_id)
            if resp is not None:
                with open('cache/data.json', 'w') as f:
                    f.write(resp.content)
            data = resp.json()
            for p in data['battles'] + data['planned_battles']:
                province_ids.setdefault(p['front_id'], []).append(p['province_id'])

            # fetch clan battles
            clan_provinces = wot.globalmap.clanprovinces(clan_id=clan_id, language='ru')
            if clan_provinces is not None:
                with open('cache/clan_provinces.json', 'w') as f:
                    f.write(json.dumps(clan_provinces.data))
            if clan_provinces:
                for p in clan_provinces[str(clan_id)]:
                    province_ids.setdefault(p['front_id'], []).append(p['province_id'])

            # fetch all provinces
            for front_id, provinces in province_ids.items():
                provinces = wot.globalmap.provinces(front_id=front_id, province_id=','.join(provinces))
                if provinces is not None:
                    with open('cache/provinces-%s.json' % front_id, 'w') as f:
                        f.write(json.dumps(provinces.data))
        except:
            raise
