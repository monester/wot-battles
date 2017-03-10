import mock
import datetime
import pytz
from django.test import TestCase

from global_map.models import Clan, Front, Province, ProvinceAssault
from global_map.management.commands.fetchdata import update_province


class ProvinceData(dict):
    def __init__(self, *args, **kwargs):
        super(ProvinceData, self).__init__(*args, **kwargs)
        self.update({
            'province_id': kwargs.get('province_id', 'test_province_id'),
            'province_name': kwargs.get('province_name', 'test_province_name'),
            'owner_clan_id': kwargs.get('owner_clan_id', None),
            'arena_id': kwargs.get('arena_id', 'test_arena_id'),
            'arena_name': kwargs.get('arena_name', 'test_arena_name'),
            'server': 'RU000',
            'prime_time': kwargs.get('prime_time', '18:15'),
            'competitors': kwargs.get('competitors', []),
            'attackers': kwargs.get('attackers', []),
            'landing_type': kwargs.get('landing_type', None),
            'round_number': int(kwargs.get('round_number', '6')),
            'active_battles': kwargs.get('active_battles', []),
            'battles_start_at': kwargs.get('battles_start_at', '2016-11-27T18:15:00'),
            'front_id': kwargs.get('front_id', 'test_front_id'),
            'status': kwargs.get('status', 'FINISHED'),
        })

    def generate_battles(self, clans=None, round_number=None, start_at=None):
        if not clans:
            clans = self['competitors'] + self['attackers']

        if not round_number:
            round_number = self['round_number']

        if not start_at:
            start_at = (
                self.get_battles_start_at() +
                datetime.timedelta(minutes=30 * (round_number - 1))
            ).replace(tzinfo=None).isoformat()

        battles_count = len(clans) - len(clans) % 2
        self['active_battles'] = []
        for i in range(0, battles_count, 2):
            self['active_battles'].append({
                'battle_reward': None,
                'clan_a': {
                    'battle_reward': 0,
                    'clan_id': clans[i],
                    'loose_elo_delta': -10,
                    'win_elo_delta': 5
                },
                'clan_b': {
                    'battle_reward': 0,
                    'clan_id': clans[i + 1],
                    'loose_elo_delta': -10,
                    'win_elo_delta': 5
                },
                'round': round_number,
                'start_at': start_at
            })
        return self

    def get_battles_start_at(self):
        dt = self['battles_start_at']
        return datetime.datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=pytz.UTC)


class TestUpdateProvince(TestCase):
    def setUp(self):
        province_data = ProvinceData()
        front = Front.objects.create(front_id=province_data['front_id'], max_vehicle_level=99)
        self.province = Province.objects.create(
            province_id=province_data['province_id'],
            front=front,
            province_name=province_data['province_name'],
            arena_id=province_data['arena_id'],
            arena_name=province_data['arena_name'],
            prime_time=province_data['prime_time'],
            server=province_data['server'],
        )
        self.clans = [
            Clan.objects.create(pk=i, tag='CLN%s' % i, title='Clan name %s' % i)
            for i in range(1, 10)
        ]

    @staticmethod
    def get_province(province_data):
        return Province.objects.get(
            province_id=province_data['province_id'],
            front__front_id=province_data['front_id'],
        )

    def test_update_fields(self):
        province_data = ProvinceData(
            arena_id='updated_arena_id',
            arena_name='updated_arena_name',
            prime_time='20:00',
        )
        update_province(self.province, province_data)
        province = self.get_province(province_data)
        assert province.arena_id == 'updated_arena_id'
        assert province.arena_name == 'updated_arena_name'
        assert province.prime_time == datetime.time(20, 0)

    def test_tournament_active(self):
        province_data = ProvinceData(
            competitors=[1, 2, 3, 4],
            round_number=1,
            owner_clan_id=5,
        )
        province_data.generate_battles()
        # import json
        # print json.dumps(province_data, indent=4)

        update_province(self.province, province_data)
        assault = self.get_province(province_data).assaults.first()
        assert len(assault.battles.all()) == 2

        # 2nd round
        province_data.update(dict(
            competitors=[1, 3],
            round_number=2,
        ))
        province_data.generate_battles()
        update_province(self.province, province_data)
        assert len(assault.battles.all()) == 3

        # 3rd round, with owner
        province_data.update(dict(
            competitors=[1],
            round_number=3,
        ))
        province_data.generate_battles([1, 5])

        update_province(self.province, province_data)
        assert len(assault.battles.all()) == 4

    def test_flow_before_prime_time(self):
        province_data = ProvinceData(attackers=[1, 2, 3])

        # set to 3 attackers
        update_province(self.province, province_data)
        assault = ProvinceAssault.objects.get(province__province_id='test_province_id', date='2016-11-27')
        assert set([i.id for i in assault.clans.all()]) == {1, 2, 3}

        # set to 2 attackers
        province_data.update({'attackers': [1, 2]})
        update_province(self.province, province_data)
        assault = ProvinceAssault.objects.get(province__province_id='test_province_id', date='2016-11-27')
        assert set([i.id for i in assault.clans.all()]) == {1, 2}

        # No clans assaulting province
        province_data.update({'attackers': []})
        with mock.patch('global_map.management.commands.fetchdata.utc_now') as dt_now:
            dt_now.return_value = datetime.datetime(2016, 11, 27, 17, 0, 0, tzinfo=pytz.UTC)
            update_province(self.province, province_data)

        # ProvinceAssault should be deleted if no clans assaulting province before prime time
        with self.assertRaises(ProvinceAssault.DoesNotExist):
            ProvinceAssault.objects.get(province__province_id='test_province_id', date='2016-11-27')

    def test_flow_in_prime_time(self):
        province_data = ProvinceData(attackers=self.clans[0:6])
