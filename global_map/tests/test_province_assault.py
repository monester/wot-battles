from django.test import TestCase
import datetime
from global_map.models import Clan, Front, Province
import mock
import pytz


class TestUpdateProvince(TestCase):
    def setUp(self):
        self.front = Front.objects.create(front_id='front_id', max_vehicle_level=99)
        self.province = Province.objects.create(
            province_id='province_id', front=self.front, province_name='province_name',
            arena_id='arena_id', arena_name='arena_name', prime_time='15:00', server='server')
        self.clans = [Clan.objects.create(pk=i, tag='CLN%s'%i) for i in range(10)]

    def test_tournament_planned_battles_no_owner(self):
        assault = self.province.assaults.create(
            prime_time='15:00', arena_id=self.province.arena_id, date='2016-11-27')
        assault.clans.add(*self.clans[0:4])
        with mock.patch('global_map.models.utc_now') as dt_now:
            dt_now.return_value = datetime.datetime(2016, 11, 27, 17, 0, 0, tzinfo=pytz.UTC)
            assert assault.planned_times == [
                assault.datetime,
                assault.datetime + datetime.timedelta(minutes=30),
            ]

    def test_tournament_planned_battles_with_owner(self):
        assault = self.province.assaults.create(
            prime_time='15:00', arena_id=self.province.arena_id, date='2016-11-27',
            current_owner=self.clans[4])
        assault.clans.add(*self.clans[0:4])
        with mock.patch('global_map.models.utc_now') as dt_now:
            dt_now.return_value = datetime.datetime(2016, 11, 27, 17, 0, 0, tzinfo=pytz.UTC)
            assert assault.planned_times == [
                assault.datetime,
                assault.datetime + datetime.timedelta(minutes=30),
                assault.datetime + datetime.timedelta(minutes=60),
            ]
