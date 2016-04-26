from __future__ import unicode_literals

from collections import defaultdict
from retrying import retry

import wargaming
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

from globalmap.functions import (
    Province as ProvinceMixin,
    Clan as ClanMixin,
)


# Create your models here.
class Clan(models.Model, ClanMixin):
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


class Province(models.Model, ProvinceMixin):
    province_id = models.CharField(max_length=255)
    region = models.CharField(max_length=4)
    province_name = models.CharField(max_length=255)
    prime_time = models.CharField(max_length=5, default='00:00')
    neighbours = models.ManyToManyField('Province')
    province_owner = models.ForeignKey(Clan, on_delete=models.SET_NULL, null=True, blank=True)
    front_id = models.CharField(max_length=255)

    # format: {'region': {'front_id': set(['province_id', ...])}}
    _wg_update = defaultdict(lambda: defaultdict(lambda: list()))

    # format: {'province_id': {'province': 'info', ...}}
    # NOTE: application using province_id as key because WG itself doesn't add front_id anywhere
    # in web and in case if save province id would be on different fronts it would break
    # WG services itself.
    _wg_cache = defaultdict(lambda: {})

    class Meta:
        index_together = [['province_id'], ['front_id']]
        unique_together = ['front_id', 'province_id']

    @classmethod
    def _mark_for_update(cls, provinces):
        p = provinces if isinstance(provinces, list) else [provinces]

        for province in provinces:
            cls._wg_update[province.region][province.front_id] = province['province_id']
        return provinces

    @classmethod
    def filter(cls, **filters):
        return cls._mark_for_update(cls.objects.filter(filters))

    @classmethod
    def get(cls, province_id, region=settings.DEFAULT_REGION):
        return _mark_for_update(cls.objects.get(province_id=province_id, region=region))

    def competitors(self):
        self._do_wg_update()
        return [i for i in self._competitors()]


class Battles(models.Model):
    province = models.ForeignKey(Province)
    start_time = models.DateTimeField()
    clan1 = models.ForeignKey(Clan)
    clan2 = models.ForeignKey(Clan, null=True)
    winner = models.ForeignKey(Clan, null=True)

    # when create this instance?
    # where to create this instance? by cron? on request?


class ProvinceHistory(models.Model):
    created = models.DateTimeField(auto_created=True)
