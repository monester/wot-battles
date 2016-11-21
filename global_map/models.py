from __future__ import unicode_literals

from django.db import models
import pytz
from datetime import datetime, timedelta
import math

import wargaming
from django.db.models.signals import pre_save
from django.db.models import Q
from django.dispatch import receiver
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.functional import cached_property

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
wgn = wargaming.WGN(settings.WARGAMING_KEY, language='ru', region='ru')


# Create your models here.
class Clan(models.Model):
    tag = models.CharField(max_length=5, null=True)
    title = models.CharField(max_length=255, null=True)
    elo_6 = models.IntegerField(null=True)
    elo_8 = models.IntegerField(null=True)
    elo_10 = models.IntegerField(null=True)

    def __repr__(self):
        return '<Clan: %s>' % self.tag

    def __str__(self):
        return repr(self)

    def force_update(self):
        clan_info = wgn.clans.info(clan_id=self.pk)[str(self.pk)]
        self.tag = clan_info['tag']
        self.title = clan_info['name']

    @classmethod
    def get_or_create(cls, clan_id=None, clan_tag=None):
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
            clan_tag = clan_tag.upper()
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

    def as_json(self):
        return {
            'clan_id': self.pk,
            'tag': self.tag,
            'name': self.title,
            'elo_6': self.elo_6,
            'elo_8': self.elo_8,
            'elo_10': self.elo_10,
        }

    def as_json_with_arena(self, arena_id):
        data = self.as_json()
        stat = self.arena_stats.filter(arena_id=arena_id)
        if stat:
            data['arena_stat'] = stat[0].as_json()
        else:
            data['arena_stat'] = ClanArenaStat(
                clan=self,
                arena_id=arena_id,
                wins_percent=0,
                battles_count=0,
            ).as_json()
        return data


class Front(models.Model):
    front_id = models.CharField(max_length=254)
    max_vehicle_level = models.IntegerField()


class Province(models.Model):
    province_id = models.CharField(max_length=255)
    front = models.ForeignKey(Front)
    province_name = models.CharField(max_length=255)
    province_owner = models.ForeignKey(Clan, on_delete=models.SET_NULL, null=True, blank=True)
    arena_id = models.CharField(max_length=255)
    arena_name = models.CharField(max_length=255)
    prime_time = models.TimeField()
    server = models.CharField(max_length=10)

    def __repr__(self):
        return '<Province: %s>' % self.province_id

    def as_json(self):
        return {
            'province_id': self.province_id,
            'province_name': self.province_name,
            'province_owner': self.province_owner.as_json(),
            'arena_id': self.arena_id,
            'arena_name': self.arena_name,
            'prime_time': self.prime_time,
            'server': self.server,
            'max_vehicle_level': self.front.max_vehicle_level,
        }


class ClanArenaStat(models.Model):
    clan = models.ForeignKey(Clan, related_name='arena_stats')
    arena_id = models.CharField(max_length=255)
    wins_percent = models.FloatField()
    battles_count = models.IntegerField()

    def as_json(self):
        return {
            'wins_percent': self.wins_percent,
            'battles_count': self.battles_count,
        }


class ProvinceAssault(models.Model):
    date = models.DateField()               # On what date Assault was performed
    province = models.ForeignKey(Province,  # On what province
                                 related_name='assaults')
    current_owner = models.ForeignKey(Clan, related_name='+', null=True)
    clans = models.ManyToManyField(Clan)    # By which clans
    prime_time = models.TimeField()
    arena_id = models.CharField(max_length=255)
    round_number = models.IntegerField()
    landing_type = models.CharField(max_length=255, null=True)

    def __repr__(self):
        return '<ProvinceAssault: %s owned by %s' % (
            self.province.province_id, self.province.province_owner.tag)

    @cached_property
    def datetime(self):
        return datetime.combine(self.date, self.prime_time).replace(tzinfo=pytz.UTC)

    @cached_property
    def planned_times(self):
        if datetime.now(tz=pytz.UTC) > self.datetime:
            round_number = self.round_number
        else:
            round_number = 1  # Bug-Fix: WGAPI return round number from previous day
        total_rounds = round_number + int(math.ceil(math.log(len(self.clans.all()), 2))) - 1
        times = [
            self.datetime + timedelta(minutes=30) * i
            for i in range(0, total_rounds)
        ]
        if self.current_owner:
            times.append(self.datetime + timedelta(minutes=30) * total_rounds)
        return times

    def clan_battles(self, clan):
        max_rounds = len(self.planned_times)
        existing_battles = {b.round_datetime: b for b in self.battles.filter(Q(clan_a=clan) | Q(clan_b=clan))}
        res = []
        for i in range(max_rounds):
            time = self.planned_times[i]
            if time in existing_battles:
                res.append(existing_battles[time])
            else:
                pb = ProvinceBattle(
                    assault=self,
                    province=self.province,
                    arena_id=self.arena_id,
                    round=i + 1,
                )
                if i == max_rounds - 1 and self.current_owner:
                    pb.clan_a = self.current_owner
                    pb.clan_b = clan
                res.append(pb)
        return res

    @cached_property
    def max_rounds(self):
        return len(self.planned_times)

    def as_clan_json(self, clan):
        battles = self.clan_battles(clan)
        return {
            'province_info': self.province.as_json(),
            'clans': {c.pk: c.as_json_with_arena(self.arena_id) for c in self.clans.all()},
            'battles': [b.as_json() for b in self.clan_battles(clan)],
        }


class ProvinceBattle(models.Model):
    assault = models.ForeignKey(ProvinceAssault, related_name='battles')
    province = models.ForeignKey(Province, related_name='battles')
    arena_id = models.CharField(max_length=255)
    clan_a = models.ForeignKey(Clan, related_name='+')
    clan_b = models.ForeignKey(Clan, related_name='+')
    winner = models.ForeignKey(Clan, null=True, related_name='battles_winner')
    start_at = models.DateTimeField()
    round = models.IntegerField()

    class Meta:
        ordering = ('round', 'start_at')

    def __repr__(self):
        clan_a_tag = clan_b_tag = province_id = None
        try:
            clan_a_tag = self.clan_a.tag
        except ObjectDoesNotExist:
            clan_a_tag = None
        try:
            clan_b_tag = self.clan_b.tag
        except ObjectDoesNotExist:
            clan_b_tag = None
        try:
            province_id = self.province.province_id
        except ObjectDoesNotExist:
            province_id = None
        return '<Battle round %s: %s VS %s on %s>' % (self.round, clan_a_tag, clan_b_tag, province_id)

    def __str__(self):
        return repr(self)

    @property
    def round_datetime(self):
        prime_time = self.province.prime_time
        date = self.assault.date
        return datetime.combine(date, prime_time).replace(tzinfo=pytz.UTC) + timedelta(minutes=30) * (self.round - 1)

    @property
    def title(self):
        power = self.assault.max_rounds - self.round - 1
        if power == 0:
            return 'Final'
        else:
            return 'Round 1 / %s' % (2 ** power)

    def as_json(self):
        try:
            clan_a = self.clan_a
        except ObjectDoesNotExist:
            clan_a = None
        try:
            clan_b = self.clan_b
        except ObjectDoesNotExist:
            clan_b = None
        return {
            'planned_start_at': self.round_datetime,
            'real_start_at': self.start_at,
            'clan_a': clan_a.as_json_with_arena(self.arena_id) if clan_a else None,
            'clan_b': clan_a.as_json_with_arena(self.arena_id) if clan_b else None,
        }


class ProvinceTag(models.Model):
    date = models.DateField()
    tag = models.CharField(max_length=255)
    province_id = models.CharField(max_length=255)

    def __repr__(self):
        return "<ProvinceTag %s: %s@%s>" % (self.date, self.tag, self.province_id)


@receiver(pre_save, sender=Clan)
def fetch_minimum_clan_info(sender, instance, **kwargs):
    if (not instance.tag or not instance.title) and instance.pk:
        instance.force_update()
