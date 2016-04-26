import math
from datetime import datetime, timedelta
from collections import defaultdict
from django.conf import settings

# battle timer before battle + maximum battle time
BATTLE_LENGTH = timedelta(minutes=15, seconds=30)
# time between battles
BATTLE_INTERVAL = timedelta(minutes=15)


class Province(object):
    # [region][front_id][province_id]
    _update_required = defaultdict(lambda: defaultdict(lambda: set()))
    # [region][province_id]
    _cache_data = defaultdict(lambda: dict())

    province_id = None
    arena_name = None
    province_name = None
    prime_time = None
    prime_datetime = None
    server = None

    def __init__(self, *args, **kwargs):
        cls = self.__class__  # used to work with cache
        cls._update_required[self.region][self.front_id].add(self.province_id)

    @classmethod
    def _update_cache(cls):
        for region, front in cls._update_required.copy().items():
            wot = settings.WOT[region]
            for front_id, prov_list in front.items():
                res = wot.globalmap.provinces(province_id=list(prov_list), front_id=front_id)
                cls._update_required[region].pop(front_id)
                for data in res:
                    province_id = data['province_id']
                    # convert all clan id to string
                    data['owner_clan_id'] = str(data['owner_clan_id'])
                    data['competitors'] = [str(i) for i in data['competitors']]
                    data['attackers'] = [str(i) for i in data['attackers']]
                    cls._cache_data[region][province_id] = data

    @property
    def _cache(self):
        cache = self.__class__._cache_data  # used to work with class cache
        try:
            return cache[self.region][self.province_id]
        except KeyError:
            self._update_cache()
            return cache[self.region][self.province_id]

    @property
    def province_id(self):
        return self._cache['province_id']

    @property
    def arena_name(self):
        return self._cache['arena_name']

    @property
    def province_name(self):
        return self._cache['province_name']

    @property
    def prime_time(self):
        return self._cache['prime_time']

    @property
    def prime_datetime(self):
        return datetime.strptime(self.prime_time, "%H:%M") \
                .replace(year=2016, second=0, microsecond=0)

    @property
    def battle_start_at_datetime(self):
        battles_start_at = self._cache['battles_start_at']
        return datetime.strptime(battles_start_at, '%Y-%m-%dT%H:%M:%S')

    @property
    def server(self):
        return self._cache['server']

    @property
    def url(self):
        return "https://%s.wargaming.net/globalmap%s" % (self._region, self._cache['uri'])

    @property
    def competitors(self):
        return self._cache['competitors']

    @property
    def rounds_count(self):
        if not self._cache['landing_type']:
            return 0

        if self._cache['landing_type'] == 'tournament':
            count = len(self._cache['competitors'])
        else:
            count = len(self._cache['attackers'])
        if count > 0:
            return int(math.ceil(math.log(count, 2)))
        return -1

    @property
    def round_times(self):
        times = {}
        for battle_time, value in self.battle_times().items():
            minute = 30 if battle_time.minute >= 30 else 0
            times[battle_time.replace(minute=minute, second=0, microsecond=0)] = value
        return times

    def attack_type(self, clan_id):
        if self._cache['owner_clan_id'] == clan_id and (
            self._cache['attackers'] or self._cache['competitors']
        ):
            result = 'Defence'
        elif clan_id in self._cache['attackers']:
            result = 'By land'
        elif clan_id in self._cache['competitors']:
            result = 'Tournament'
        else:
            result = 'Unknown'
        return result

    def battle_times(self, clan_id=None):
        """Is it useful function?"""
        rounds_count = self.rounds_count
        if rounds_count == -1:
            return {}

        battles_start_at = self.battle_start_at_datetime
        if self._cache['owner_clan_id'] == clan_id:
            times = {battles_start_at + timedelta(minutes=30) * rounds_count: 0}
        else:
            times = {}
            for i in range(rounds_count + 1):
                times[battles_start_at + timedelta(minutes=30) * i] = int(math.pow(2, rounds_count - i - 1))
        return times

    def has_battle_at(self, time):
        """Is it useful function?"""
        for bt in self.battle_times().keys():
            # 18:00:00 <= bt <= 18:29:59
            if time <= bt < time + timedelta(minutes=30):
                return True
        return False

    def at(self, time):
        """Is it useful function?"""
        res = self._cache.copy()
        res['url'] = self.url
        res['time'] = time
        return res

    def __repr__(self):
        return "<Province '%s' front_id '%s' region '%s'>" % (
            self.province_id,
            self.front_id,
            self.region,
        )

    def __getitem__(self, item):
        return self._cache[item]

    def __getattr__(self, item):
        if item in ['keys', 'values', 'items', 'copy']:
            return getattr(self._cache, item)
        raise AttributeError('%s object has no attribute %s' % (self.__class__.__name__, item))


class Clan(object):
    # [region][clan_id]
    _update_required = defaultdict(lambda: set())
    # [region][clan_id]
    _cache_data = defaultdict(lambda: dict())

    def __init__(self):
        cls = self.__class__  # used to work with cache
        cls._update_required[self.region].add(self.clan_id)

    @property
    def _cache(self):
        data = self.__class__._cache_data  # used to work with cache
        try:
            return data[self.region][self.clan_id]
        except KeyError:
            self._update_cache()
            return data[self.region][self.clan_id]

    @classmethod
    def _update_cache(cls):
        for region, clans in cls._update_required.copy().items():
            wgn = settings.WGN[region]
            res = wgn.clans.info(clan_id=list(clans))
            cls._update_required[region].pop(region)
            cls._cache_data[region].update(res)

    def clan_battles(self):
        clan_id = self.clan_id
        data = self.wot.globalmap.wg_clan_battles(clan_id)
        province_list = defaultdict(lambda: [])  # list of all provinces we have any actions, by front

        for battle_type in ['battles', 'planned_battles']:
            for battle in data[battle_type]:
                province_list[battle['front_id']].append(battle['province_id'])
        return data

    def __getitem__(self, item):
        return self._cache[item]
