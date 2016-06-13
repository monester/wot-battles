import math
from datetime import datetime, timedelta
from collections import defaultdict
from django.conf import settings

# battle timer before battle + maximum battle time
BATTLE_LENGTH = timedelta(minutes=15, seconds=40)
# time between battles
BATTLE_INTERVAL = timedelta(minutes=15)


class Province(object):

    province_id = None
    arena_name = None
    province_name = None
    prime_time = None
    prime_datetime = None
    server = None



class Clan(object):

    def __init__(self):
        cls = self.__class__  # used to work with cache
        cls._update_required[self.region].add(self.clan_id)

