# coding=utf-8
from __future__ import unicode_literals

from django.db import models
import pytz
import requests

from datetime import timedelta
import datetime
import math

import wargaming
from django.db.models.signals import pre_save
from django.db.models import Q
from django.contrib.postgres.fields import JSONField
from django.dispatch import receiver
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.functional import cached_property

wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
wgn = wargaming.WGN(settings.WARGAMING_KEY, language='ru', region='ru')


def utc_now():
    return datetime.datetime.now(tz=pytz.UTC)


def combine_dt(date, time):
    return datetime.datetime.combine(date, time)


class TournamentInfo(dict):
    def __init__(self, province_id, seq=None, **kwargs):
        super(TournamentInfo, self).__init__(seq=None, **kwargs)
        # {u'applications_decreased': False,
        #  u'apply_error_message': u'Чтобы подать заявку, войдите на сайт.',
        #  u'arena_name': u'Аэродром',
        #  u'available_applications_number': 0,
        #  u'battles': [],
        #  u'can_apply': False,
        #  u'front_id': u'campaign_05_ru_west',
        #  u'is_apply_visible': False,
        #  u'is_superfinal': False,
        #  u'next_round': None,
        #  u'next_round_start_time': u'19:15:00.000000',
        #  u'owner': None,
        #  u'pretenders': [{u'arena_battles_count': 49,
        #    u'arena_wins_percent': 38.78,
        #    u'cancel_action_id': None,
        #    u'clan_id': 94365,
        #    u'color': u'#b00a10',
        #    u'division_id': None,
        #    u'elo_rating_10': 1155,
        #    u'elo_rating_6': 1175,
        #    u'elo_rating_8': 1259,
        #    u'emblem_url': u'https://ru.wargaming.net/clans/media/clans/emblems/cl_365/94365/emblem_64x64_gm.png',
        #    u'fine_level': 0,
        #    u'id': 94365,
        #    u'landing': True,
        #    u'name': u'Deadly Decoy',
        #    u'tag': u'DECOY',
        #    u'xp': None}],
        #  u'province_id': u'herning',
        #  u'province_name': u'\u0425\u0435\u0440\u043d\u0438\u043d\u0433',
        #  u'province_pillage_end_datetime': None,
        #  u'province_revenue': 0,
        #  u'revenue_level': 0,
        #  u'round_number': 1,
        #  u'size': 32,
        #  u'start_time': u'19:00:00',
        #  u'turns_till_primetime': 11}
        self.update(requests.get(
            'https://ru.wargaming.net/globalmap/game_api/tournament_info?alias=%s' % province_id).json())
        try:
            province = Province.objects.get(province_id=self['province_id'], front__front_id=self['front_id'])
        except Province.DoesNotExist:
            return

        arena_id = province.arena_id
        owner = self['owner']
        if owner:
            update_clan_province_stat(arena_id, **owner)

        for clan_data in self.clans_info.values():
            update_clan_province_stat(arena_id, **clan_data)

    @property
    def clans_info(self):
        clans = {}
        for battle in self['battles']:
            if 'first_competitor' in battle and battle['first_competitor']:
                clans[battle['first_competitor']['id']] = battle['first_competitor']
            if 'second_competitor' in battle and battle['second_competitor']:
                clans[battle['second_competitor']['id']] = battle['second_competitor']
        if isinstance(self['pretenders'], list):
            for clan in self['pretenders']:
                clans[clan['id']] = clan
        if self['owner'] and self['owner']['id'] in clans:
            del clans[self['owner']['id']]
        return clans

    @property
    def pretenders(self):
        return self.clans_info.keys()


def update_clan_province_stat(arena_id, tag, name, elo_rating_6, elo_rating_8, elo_rating_10,
                              arena_wins_percent, arena_battles_count, **kwargs):
        pk = kwargs.get('id') or kwargs['clan_id']

        clan = Clan.objects.update_or_create(id=pk, defaults={
            'tag': tag, 'title': name,
            'elo_6': elo_rating_6, 'elo_8': elo_rating_8,
            'elo_10': elo_rating_10,
        })[0]
        ClanArenaStat.objects.update_or_create(clan=clan, arena_id=arena_id, defaults={
            'wins_percent': arena_wins_percent,
            'battles_count': arena_battles_count,
        })


class Clan(models.Model):
    tag = models.CharField(max_length=5, null=True)
    title = models.CharField(max_length=255, null=True)
    elo_6 = models.IntegerField(null=True)
    elo_8 = models.IntegerField(null=True)
    elo_10 = models.IntegerField(null=True)

    def __repr__(self):
        return '<Clan: %s>' % self.tag

    def __str__(self):
        return self.tag

    def force_update(self):
        clan_info = wgn.clans.info(clan_id=self.pk)[str(self.pk)]
        self.tag = clan_info['tag']
        self.title = clan_info['name']
        self.save()

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

    def __str__(self):
        return self.province_id

    def force_update(self):
        data = wot.globalmap.provinces(
            front_id=self.front.front_id, province_id=self.province_id,
            fields='arena_id,arena_name,province_name,prime_time,owner_clan_id,server')

        if len(data) == 0:
            raise Exception("Province '%s' not found on front '%s'", self.province_id, self.front.front_id)
        data = data[0]

        self.arena_id = data['arena_id']
        self.arena_name = data['arena_name']
        self.province_name = data['province_name']
        self.prime_time = data['prime_time']
        if data['owner_clan_id']:
            self.province_owner = Clan.objects.get_or_create(pk=data['owner_clan_id'])[0]
        self.server = data['server']

    @cached_property
    def tournament_info(self):
        return TournamentInfo(self.province_id)

    def as_json(self):
        return {
            'province_id': self.province_id,
            'province_name': self.province_name,
            'province_owner': self.province_owner and self.province_owner.as_json(),
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


# CLEAN MAP
# [{u'active_battles': [],
#   u'arena_id': u'10_hills',
#   u'arena_name': u'\u0420\u0443\u0434\u043d\u0438\u043a\u0438',
#   u'attackers': [],
#   u'battles_start_at': u'2016-11-23T19:15:00',
#   u'competitors': [192,
#    3861,
#    45846,
#    61752,
#    80424,
#    82433,
#    146509,
#    170851,
#    179351,
#    190526,
#    200649,
#    201252,
#    219575],
#   u'current_min_bet': 0,
#   u'daily_revenue': 0,
#   u'front_id': u'campaign_05_ru_west',
#   u'front_name': u'\u041a\u0430\u043c\u043f\u0430\u043d\u0438\u044f: \u0417\u0430\u043f\u0430\u0434',
#   u'is_borders_disabled': False,
#   u'landing_type': u'tournament',
#   u'last_won_bet': 0,
#   u'max_bets': 32,
#   u'neighbours': [u'herning', u'odense', u'uddevalla'],
#   u'owner_clan_id': None,
#   u'pillage_end_at': None,
#   u'prime_time': u'19:15',
#   u'province_id': u'aarhus',
#   u'province_name': u'\u041e\u0440\u0445\u0443\u0441',
#   u'revenue_level': 0,
#   u'round_number': None,
#   u'server': u'RU6',
#   u'status': None,
#   u'uri': u'/#province/aarhus',
#   u'world_redivision': False}]

class ProvinceAssault(models.Model):
    date = models.DateField()               # On what date Assault was performed
    province = models.ForeignKey(Province,  # On what province
                                 related_name='assaults')
    current_owner = models.ForeignKey(Clan, related_name='+', null=True)
    clans = models.ManyToManyField(Clan)    # By which clans
    prime_time = models.TimeField()
    arena_id = models.CharField(max_length=255)
    round_number = models.IntegerField(null=True)
    landing_type = models.CharField(max_length=255, null=True)
    status = models.CharField(max_length=20, default='FINISHED', null=True)
    division = JSONField(null=True)

    class Meta:
        ordering = ('date', )
        unique_together = ('date', 'province')

    def __repr__(self):
        return '<ProvinceAssault @%s: %s owned by %s>' % (
            self.date, self.province.province_id, str(self.current_owner))

    @cached_property
    def datetime(self):
        if isinstance(self.date, str):
            self.date = datetime.date(*[int(i) for i in self.date.split('-')])
        if isinstance(self.prime_time, str):
            self.prime_time = datetime.time(*[int(i) for i in self.prime_time.split(':')])
        return combine_dt(self.date, self.prime_time).replace(tzinfo=pytz.UTC)

    @cached_property
    def planned_times(self):
        if utc_now() > self.datetime:
            if isinstance(self.round_number, int):
                round_number = self.round_number
            else:
                # Bug-fix: WGAPI can return None on round number if map is new
                round_number = 1
        else:
            round_number = 1  # Bug-Fix: WGAPI return round number from previous day

        clans_count = len(self.clans.all())
        if clans_count > 0:
            total_rounds = round_number + int(math.ceil(math.log(clans_count, 2))) - 1
        else:
            total_rounds = round_number - 1
        times = [
            self.datetime + timedelta(minutes=30) * i
            for i in range(0, total_rounds)
        ]
        if self.current_owner:
            times.append(self.datetime + timedelta(minutes=30) * total_rounds)
        return times

    def clan_battles(self, clan):
        max_rounds = len(self.planned_times)
        existing_battles = {b.round: b for b in self.battles.filter(Q(clan_a=clan) | Q(clan_b=clan))}

        res = []
        for round_number in range(1, max_rounds + 1):
            if round_number in existing_battles:
                res.append(existing_battles[round_number])
            else:
                # create FAKE planned battle
                pb = ProvinceBattle(
                    assault=self,
                    province=self.province,
                    arena_id=self.arena_id,
                    round=round_number,
                )
                if round_number <= self.round_number and self.status == 'STARTED':
                    pb.winner = clan
                if round_number == max_rounds and self.current_owner:
                    pb.clan_a = self.current_owner
                    pb.clan_b = clan
                res.append(pb)
        return res

    @cached_property
    def max_rounds(self):
        return len(self.planned_times)

    def as_clan_json(self, clan, current_only=True):
        if current_only:
            battles = [b.as_json() for b in self.clan_battles(clan)
                       if b.round >= self.round_number and self.status != 'FINISHED'
                       or self.datetime > utc_now()]
        else:
            battles = [b.as_json() for b in self.clan_battles(clan)]

        if self.current_owner == clan:
            mode = 'defence'
            battles = battles[-1:-2:-1]
        else:
            mode = 'attack'
        return {
            'mode': mode,
            'province_info': self.province.as_json(),
            'prime_time': self.datetime,
            'clans': {c.pk: c.as_json_with_arena(self.arena_id) for c in self.clans.all()},
            'battles': battles,
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
        return combine_dt(date, prime_time).replace(tzinfo=pytz.UTC) + timedelta(minutes=30) * (self.round - 1)

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
            'clan_b': clan_b.as_json_with_arena(self.arena_id) if clan_b else None,
            'winner': self.winner.as_json() if self.winner else None
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
    elif not instance.pk and instance.tag:
        info = [i for i in wgn.clans.list(search=instance.tag) if i['tag'] == instance.tag]
        if len(info) == 1:
            instance.pk = info[0]['clan_id']
            instance.title = info[0]['name']
        else:
            # No clan with such tag, do not allow such Clan
            instance.tag = None
            instance.title = None


@receiver(pre_save, sender=Province)
def fetch_minimum_clan_info(sender, instance, **kwargs):
    required_fields =  ['province_name', 'arena_id', 'arena_name', 'prime_time', 'server']
    for field in required_fields:
        if not getattr(instance, field):
            instance.force_update()
