from __future__ import unicode_literals

from django.db import models

import wargaming
import json
# WARGAMING_KEY = '2f9b826b353eb63d993d6f0d1653c5ff' # server
WARGAMING_KEY = '540da2676c01efaee6c4c59c7a0f0f52' # mobile
wot = wargaming.WoT(WARGAMING_KEY, base_url='https://api.worldoftanks.ru/wot/')
wgn = wargaming.WGN(WARGAMING_KEY, base_url='https://api.worldoftanks.ru/wgn/')


# Create your models here.
class Clan(models.Model):
    tag = models.CharField(max_length=5, unique=True)
    title = models.CharField(max_length=255)

    def __repr__(self):
        return '<Clan: %s>' % self.tag

    @classmethod
    def get_or_create(cls, clan_id=None, clan_tag=None):
        clan_tag = clan_tag.upper()
        if clan_id and not isinstance(clan_id, str):
            clan_id = str(clan_id)

        if clan_id:
            clan_obj, created = cls.objects.get_or_create(id=int(clan_id))
            if created:
                info = wgn.clans.info(clan_id=clan_id)
                if clan_id not in info:
                    clan_obj.delete()
                    return None
                clan_obj.tag = info[clan_id]['tag']
                clan_obj.title = info[clan_id]['name']
                clan_obj.save()
        elif clan_tag:
            try:
                clan_obj = cls.objects.get(tag=clan_tag)
            except Exception:
                search = wgn.clans.list(search='[%s]' % clan_tag)
                search = [s for s in search if s['tag'] == clan_tag]
                if len(search) == 1:
                    clan_obj = cls.objects.create(
                        id=search[0]['clan_id'],
                        tag=clan_tag,
                        title=search[0]['name']
                    )
                else:
                    return None
        else:
            raise Exception('Should specify clan_id or clan_tag')
        return clan_obj


class Province(models.Model):
    province_id = models.CharField(max_length=255)
    province_name = models.CharField(max_length=255)
    province_owner = models.ForeignKey(Clan, on_delete=models.SET_NULL, null=True, blank=True)
    front_id = models.CharField(max_length=255, default='1604_ru_event_west')

    _need_update = []

    @classmethod
    def list_all(cls):

        pass
