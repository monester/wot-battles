from __future__ import unicode_literals

from collections import defaultdict
from retrying import retry

import wargaming
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import pre_init, post_init, pre_save


class Clan(models.Model):
    # [region][clan_id]
    _update_required = defaultdict(lambda: set())
    # [region][clan_id]
    _cache_data = defaultdict(lambda: dict())
    _wg_clan_battles_cache = defaultdict(lambda: dict())
    _clan_provinces_cache = defaultdict(lambda: dict())

    clan_id = models.CharField(max_length=20)
    region = models.CharField(max_length=4)
    tag = models.CharField(max_length=5)
    title = models.CharField(max_length=255)

    class Meta:
        unique_together = ['region', 'tag']

    def __repr__(self):
        return '<Clan: [%s] region:%s>' % (self.tag, self.region)

    def __init__(self, *args, **kwargs):
        super(Clan, self).__init__(*args, **kwargs)
        self.wot = settings.WOT[self.region]
        self.wgn = settings.WGN[self.region]

    @classmethod
    def get_or_create(cls, clan_id=None, clan_tag=None, region=settings.DEFAULT_REGION):
        # TODO: refactor to post_init fetch clan_id
        # TODO: refactor to post_save fetch full clan info
        try:
            if clan_id:
                return cls.objects.get(clan_id=str(clan_id))
            elif clan_tag:
                return cls.objects.get(tag=clan_tag)
            else:
                raise Exception('Should specify clan_id or clan_tag')
        except ObjectDoesNotExist:
            pass

        # clan isn't in database query to WG
        wgn = settings.WGN[region]
        params = {}
        if clan_id:
            clan_id = str(clan_id)
            info = wgn.clans.info(clan_id=clan_id)[clan_id]
            if not info:
                raise Exception('Clan not found')
        else:
            params['tag'] = clan_tag
            search = wgn.clans.list(search=('[%s]' % clan_tag))
            search = [s for s in search if s and s['tag'] == clan_tag]
            if not search:
                raise Exception('Clan not found')
            info = search[0]

        return cls.objects.create(
            clan_id=info['clan_id'],
            tag=info['tag'],
            title=info['name'],
            region=region,
        )

    @classmethod
    def _update_cache(cls):
        """Cache updater class"""
        for region, clans in cls._update_required.copy().items():
            wgn = settings.WGN[region]
            res = wgn.clans.info(clan_id=list(clans))
            cls._update_required.pop(region)
            cls._cache_data[region].update(res)

    @property
    def _cache(self):
        """Cache fetcher class"""
        data = self.__class__._cache_data  # used to work with cache
        try:
            return data[self.region][self.clan_id]
        except KeyError:
            self._update_cache()
            return data[self.region][self.clan_id]

    def clan_provinces(self):
        """Clan owned provinces"""
        clan_id = self.clan_id
        try:
            return self.__class__._clan_provinces_cache[self.region][clan_id]
        except KeyError:
            pass

        provinces = self.wot.globalmap.clanprovinces(clan_id=clan_id)[clan_id]
        province_list = {}  # list of all provinces we have any actions, by front

        for province in provinces:
            province_list[province['province_id']], _ = Province.objects.get_or_create(
                province_id=province['province_id'],
                front_id=province['front_id'],
                region=self.region,
            )
        self.__class__._clan_provinces_cache[self.region][clan_id] = province_list
        return province_list

    def clan_neighbor_provinces(self):
        """Provinces next to clan's owned"""
        neighbors = {}
        for province in self.clan_provinces().values():
            for neighbor in province.neighbours.all():
                neighbors[neighbor.province_id] = Province.objects.get_or_create(
                    province_id=neighbor.province_id,
                    front_id=neighbor.front_id,
                    region=self.region,
                )
        return neighbors

    def clan_battles(self):
        clan_id = self.clan_id
        try:
            return self.__class__._wg_clan_battles_cache[self.region][clan_id]
        except KeyError:
            pass
        data = self.wot.globalmap.wg_clan_battles(clan_id)
        province_list = {}  # list of all provinces we have any actions, by front

        # 1. Generate province list where clan can have battles
        # 2. Query for province if clan is in competitors, attackers
        # 3. Check if own province and competitors and attackers lists aren't empty

        # UnOfficial API call
        for battle_type in ['battles', 'planned_battles']:
            for battle in data[battle_type]:
                province_list[battle['province_id']], _ = Province.objects.get_or_create(
                    province_id=battle['province_id'],
                    front_id=battle['front_id'],
                    region=self.region,
                )
                print province_list[battle['province_id']]
        self.__class__._wg_clan_battles_cache[self.region][clan_id] = province_list

        # Battle for owned provinces
        # for i in self._clan_provinces():
        #     Province()
        # Battle for neighbor provinces
        return province_list

    def __getitem__(self, item):
        return self._cache[item]

    def __getattr__(self, item):
        if item in ['keys', 'values', 'items', 'copy']:
            return getattr(self._cache, item, None)
        raise AttributeError('%s object has no attribute %s' % (self.__class__.__name__, item))


class Province(models.Model):
    # Structure: [region][front_id][province_id]
    _update_required = defaultdict(lambda: defaultdict(lambda: set()))
    # Structure: [region][province_id]
    _cache_data = defaultdict(lambda: dict())

    province_id = models.CharField(max_length=255)
    region = models.CharField(max_length=4)
    province_name = models.CharField(max_length=255)
    prime_time = models.CharField(max_length=5, default='00:00')
    neighbours = models.ManyToManyField('Province')
    province_owner = models.ForeignKey(Clan, on_delete=models.SET_NULL, null=True, blank=True, related_name='provinces')
    front_id = models.CharField(max_length=255)

    class Meta:
        index_together = [['region', 'province_id'],
                          ['region', 'province_id', 'front_id']]
        unique_together = ['region', 'province_id']

    @classmethod
    def _update_cache(cls):
        for region, front in cls._update_required.copy().items():
            wot = settings.WOT[region]
            for front_id, prov_list in front.items():
                res = wot.globalmap.provinces(province_id=list(prov_list), front_id=front_id)
                for data in res:
                    province_id = data['province_id']
                    # convert all clan id to string
                    data['owner_clan_id'] = str(data['owner_clan_id'])
                    data['competitors'] = [str(i) for i in data['competitors']]
                    data['attackers'] = [str(i) for i in data['attackers']]
                    cls._cache_data[region][province_id] = data
                cls._update_required[region].pop(front_id)

    @classmethod
    def mark_for_update(cls, region, front_id, province_id):
        cls._update_required[region][front_id].add(province_id)

    @property
    def _cache(self):
        cache = self.__class__._cache_data  # used to work with class cache
        try:
            return cache[self.region][self.province_id]
        except KeyError:
            self._update_cache()
            return cache[self.region][self.province_id]

    @property
    def prime_datetime(self):
        return datetime.strptime(self.prime_time, "%H:%M").replace(year=2016, second=0, microsecond=0)

    @property
    def battle_start_at_datetime(self):
        return datetime.strptime(self._cache['battles_start_at'], '%Y-%m-%dT%H:%M:%S')

    @property
    def url(self):
        return "https://%s.wargaming.net/globalmap%s" % (self._region, self._cache['uri'])

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
            return getattr(self._cache, item, None)
        raise AttributeError('%s object has no attribute %s' % (self.__class__.__name__, item))


class Battles(models.Model):
    province = models.ForeignKey(Province, related_name='battles')
    battle_date = models.DateField()
    start_time = models.DateTimeField()
    clan1 = models.ForeignKey(Clan, related_name='+')
    clan2 = models.ForeignKey(Clan, related_name='+', null=True)
    winner = models.ForeignKey(Clan, related_name='+', null=True)

    class Meta:
        index_together = [
            ['province'], ['battle_date'], ['clan1'], ['clan2'], ['winner']
        ]


class ProvinceHistory(models.Model):
    created = models.DateTimeField(auto_created=True)


@receiver(post_init, sender=Province)
def mark_for_update(sender, instance, **kwargs):
    sender.mark_for_update(instance.region, instance.front_id, instance.province_id)
    if not instance.pk:
        data = instance._cache
        for i in ['province_id', 'province_name', 'prime_time', 'front_id']:
            setattr(instance, i, data[i])
        instance.province_owner = Clan.get_or_create(clan_id=data['owner_clan_id'], region=instance.region)
