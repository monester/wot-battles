from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.postgres.fields import ArrayField

from wgn import Clan
from wot_clan_battles.utils import get_today, get_date, get_datetime
from datetime import datetime

from .globalmap_base import ProvinceBase, FrontBase


class Season(models.Model):
    season_name = models.CharField(max_length=255)
    season_id = models.CharField(max_length=255)
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(choices=(('PLANNED', 'PLANNED'), ('ACTIVE', 'ACTIVE'), ('FINISHED', 'FINISHED')),
                              max_length=10)

    @property
    def fronts(self):
        return self.front_set

    @fronts.setter
    def fronts(self, value):
        for i in value:
            Front.objects.get_or_create(**i)


class Front(FrontBase):
    pass


class Province(ProvinceBase):
    province_id = models.CharField(max_length=255, primary_key=True)

    @property
    def active_battles(self):
        return self.province_battles.today()

    @active_battles.setter
    def active_battles(self, value):
        """
        :param value: list with active battles
        :type value: list
        """

        # TODO: check for existence, because we call save here
        # TODO BUG: if province doesn't exists in DB it would fail

        clan_ids = []
        for i in value:
            clan_ids.extend([i.get(j).get('clan_id') for j in ['clan_a', 'clan_b']])

        clan_ids = set(clan_ids)
        clans = Clan.objects.filter(clan_id__in=clan_ids)
        if len(clan_ids) != len(clans):
            for clan_id in clan_ids:
                Clan.objects.get_or_create(clan_id=clan_id)

        exists = self.active_battles
        for battle in value:
            flatten_dict = {k: v for k, v in battle.items() if not isinstance(v, dict)}
            flatten_dict['start_at'] = get_datetime(flatten_dict['start_at'])
            for k, v in battle.items():
                if not isinstance(v, dict):
                    continue
                for k2, v2 in v.items():
                    flatten_key = '%s_%s' % (k, k2)
                    flatten_dict[flatten_key] = v2
            pb = ProvinceBattle(**flatten_dict)
            pb.date = get_today()
            pb.province = self

            if pb not in exists:
                pb.save()

    @property
    def attackers(self):
        return self.attackers_by_date.today().clans

    @attackers.setter
    def attackers(self, value):
        clans = self.attackers_by_date.today().clans
        existing = {i.clan_id: i for i in Clan.objects.filter(clan_id__in=value)}
        for i in value:
            if i not in existing:
                existing[i] = Clan.objects.create(clan_id=i)
            clans.add(existing[i])

    @property
    def competitors(self):
        return self.competitors_by_date.today().clans

    @competitors.setter
    def competitors(self, value):
        clans = self.competitors_by_date.today().clans
        existing = {i.clan_id: i for i in Clan.objects.filter(clan_id__in=value)}
        for i in value:
            if i not in existing:
                existing[i] = Clan.objects.create(clan_id=i)
            clans.add(existing[i])

    def __repr__(self):
        return "<Province: %s>" % self.province_id


# Stats Section
class ProvinceManager(models.Manager):
    use_for_related_fields = True
    today_obj = None

    def today(self):
        if not self.today_obj:
            now = datetime.now(tz=pytz.UTC).replace(microsecond=0, second=0)
            prime_time = self.instance.prime_time
            prime = now.replace(**prime_time)
            date = get_today()
            if now > prime and self.instance.status != 'RUNNING':
                date = date + timedelta(days=1)
            try:
                obj = self.get(province=self.instance, date=date)
            except ObjectDoesNotExist:
                obj = None
            self.today_obj = obj
        return self.today_obj


class ProvinceStat(ProvinceBase):
    province = models.ForeignKey('wgdb.Province', related_name='stats')

    objects = ProvinceManager()

    def __repr__(self):
        return "<ProvinceStat: %s @ %s>" % (self.province_id, self.battles_start_at)

    class Meta:
        unique_together = ("battles_start_at", "province")


class ProvinceAttackersByDate(models.Model):
    province = models.ForeignKey(Province, related_name='attackers_by_date')
    date = models.DateField()
    clans = models.ManyToManyField('wgdb.Clan')

    objects = ProvinceManager()

    class Meta:
        index_together = [
            ["province", "date"],
        ]


class ProvinceCompetitorsByDate(models.Model):
    province = models.ForeignKey(Province, related_name='competitors_by_date')
    date = models.DateField()
    clans = models.ManyToManyField('wgdb.Clan')

    objects = ProvinceManager()

    class Meta:
        index_together = [
            ["province", "date"],
        ]


# Battle Section
class ProvinceBattleManager(models.Manager):
    use_for_related_fields = True

    def today(self):
        return self.filter(province=self.instance, date=get_today())


class ProvinceBattle(models.Model):
    province = models.ForeignKey(Province, related_name='province_battles')
    date = models.DateField()
    round = models.IntegerField()
    battle_reward = models.IntegerField(null=True)

    clan_a_clan = models.ForeignKey(Clan, related_name='+')
    clan_a_loose_elo_delta = models.IntegerField(null=True)
    clan_a_win_elo_delta = models.IntegerField(null=True)

    clan_b_clan = models.ForeignKey(Clan, related_name='+')
    clan_b_loose_elo_delta = models.IntegerField(null=True)
    clan_b_win_elo_delta = models.IntegerField(null=True)

    start_at = models.DateTimeField()

    objects = ProvinceBattleManager()

    def __eq__(self, other):
        return all([
            getattr(self, attr) == getattr(other, attr, None)
            for attr in ['province', 'date', 'round', 'clan_a_clan_id', 'clan_b_clan_id']
        ])

    def __repr__(self):
        return "<ProvinceBattles: %s @ %s : %s vs %s" % (
            getattr(self.province, 'province_id', None),
            self.date, getattr(self.clan_a_clan, 'clan_id'), getattr(self.clan_b_clan, 'clan_id'))

    class Meta:
        index_together = [
            ["province", "date"],
            ["province", "date", "round"],
        ]
