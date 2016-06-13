import pytest
from wargaming.exceptions import RequestError
from collections import defaultdict


def make_province(**kwargs):
    data = {}
    # List type
    for i in ['active_battles', 'attackers', 'competitors', 'neighbours']:
        data[i] = kwargs.get(i, [])

    # String type
    for i in ['status', 'front_name', 'arena_name', 'province_name', 'arena_id', 'prime_time', 'battles_start_at',
              'pillage_end_at', 'province_id', 'uri', 'server', 'front_id']:
        data[i] = kwargs.get(i, u'')

    # boolean type
    for i in ['is_borders_disabled', 'world_redivision']:
        data[i] = kwargs.get(i, False)

    # Int type
    for i in ['max_bets', 'last_won_bet', 'current_min_bet', 'owner_clan_id', 'revenue_level',
              'daily_revenue', 'round_number']:
        data[i] = kwargs.get(i, 0)

    data['landing_type'] = kwargs.get('landing_type', None)
    return data


@pytest.fixture(autouse=True)
def wot(monkeypatch):
    class Wot(object):
        def __init__(self):
            self.globalmap = self.GlobalMap()

        class GlobalMap(object):
            @staticmethod
            def provinces(*args, **kwargs):
                if 'front_id' not in kwargs:
                    raise RequestError("Required front is is missing")
                return [make_province(province_id=province_id, front_id=kwargs['front_id'])
                        for province_id in kwargs['province_id']]

    settings = type('settings', (), {'WOT': defaultdict(lambda: Wot())})

    monkeypatch.setattr('globalmap.models.settings', settings)
