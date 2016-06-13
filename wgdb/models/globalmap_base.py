from django.db import models
from django.contrib.postgres.fields import ArrayField


class ProvinceBase(models.Model):
    arena = models.ForeignKey('wgdb.Arena', related_name='%(class)ss')
    battles_start_at = models.DateTimeField(null=True)
    current_min_bet = models.IntegerField(null=True)
    daily_revenue = models.IntegerField(null=True)
    front = models.ForeignKey('wgdb.Front', related_name='%(class)ss')
    is_borders_disabled = models.BooleanField(default=False)
    landing_type = models.CharField(max_length=255, null=True)  # tournament, etc
    last_won_bet = models.IntegerField(null=True)
    max_bets = models.IntegerField(null=True)
    neighbours = models.ManyToManyField('wgdb.Province', related_name='+')
    owner_clan = models.ForeignKey('wgdb.Clan', related_name='owned_%(class)ss', null=True)
    pillage_end_at = models.DateTimeField(null=True)
    prime_time = models.TimeField(null=True)  # 18:00
    province_name = models.CharField(max_length=255, null=True)
    revenue_level = models.IntegerField(null=True)
    round_number = models.IntegerField(null=True)
    server = models.CharField(max_length=10, null=True)  # RU1 ...
    status = models.CharField(max_length=20, null=True)  # FINISHED, etc.
    uri = models.CharField(max_length=255, null=True)
    world_redivision = models.BooleanField(default=False)

    class Meta:
        abstract = True


class FrontBase(models.Model):
    season = models.ForeignKey('wgdb.Season')
    battle_time_limit = models.IntegerField(default=0)
    division_cost = models.IntegerField(default=0)
    fog_of_war = models.BooleanField(default=True)
    front_id = models.CharField(max_length=255, primary_key=True)
    front_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_event = models.BooleanField(default=False)
    max_tanks_per_division = models.IntegerField(default=0)
    max_vehicle_level = models.IntegerField(default=0)
    min_tanks_per_division = models.IntegerField(default=0)
    min_vehicle_level = models.IntegerField(default=0)
    provinces_count = models.IntegerField(default=0)
    vehicle_freeze = models.BooleanField(default=True)

    class Meta:
        abstract = True
