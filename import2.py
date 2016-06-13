#!/usr/bin/env python

import os
from datetime import datetime
import pytz
import re

import django
from django.db import models, transaction
from django.core.exceptions import ObjectDoesNotExist
from wot_clan_battles.utils import get_date, get_datetime

import argparse
import math
import logging

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def create(cls, data, params, save=True):
    data = data.copy()
    try:
        obj = cls.objects.get(**params)
    except ObjectDoesNotExist:
        obj = cls(**params)

    fields_names = [f.name for f in cls._meta.get_fields()]
    for name in fields_names:
        if name not in data:
            name_id = "%s_id" % name
            if name_id in data:
                value = data.pop(name_id)
            else:
                continue
        else:
            value = data.pop(name)
        if name in fields_names:
            field = cls._meta.get_field(name)
            if type(field) == models.DateField:
                value = get_date(value)
            elif type(field) == models.DateTimeField:
                value = get_datetime(value)
            elif isinstance(field, models.IntegerField):
                value = int(value)
        setattr(obj, name, value)

    if save:
        with transaction.atomic():
            obj.save()
            for name in data:
                setattr(obj, name, data[name])

    return obj


def sync_clans():
    all_clans = Clan.objects.all()

    clans = {}
    for page_no in range(0, len(all_clans), 100):
        clans.update(wgn.clans.info(clan_id=[i.clan_id for i in all_clans[page_no:page_no+100]]))


def sync_players():
    pass


def sync():
    arenas = {}
    fronts = {}

    logger.debug("Import arenas")
    for key, arena in dict(wot.encyclopedia.arenas()).items():
        arenas[key] = create(Arena, arena, dict(arena_id=arena['arena_id']), save=True)
    logger.debug("Import arenas done, count: %s" % len(arenas))

    logger.debug("Import seasons")
    active_season = None
    season_count = 0
    for season in wot.globalmap.seasons():
        # obj = create(Season, season, dict(season_id=season['season_id']), save=True)
        del season['fronts']
        obj, _ = Season.objects.get_or_create(**season)
        season_count += 1
        if obj.status == 'ACTIVE':
            active_season = obj
    logger.debug("Import seasons done, count: %s" % season_count)

    logger.debug("Importing fronts and provinces")
    province_dict = {}
    for front in wot.globalmap.fronts():
        fronts[front['front_id']] = create(Front, front, dict(front_id=front['front_id'], season=active_season))

        province_count = 0
        page_no = 1
        while True:
            provinces = wot.globalmap.provinces(front_id=front['front_id'], page_no=page_no)
            if len(provinces) == 0:
                break
            province_count += len(provinces)
            for province in provinces:
                province_dict[province['province_id']] = province
                # params = dict(
                #     front=fronts[front['front_id']],
                #     province_id=province['province_id']
                # )
                # province['arena'] = arenas[province['arena_id']]
                #
                extra_data = {i:province.pop(i)
                    for i in ['active_battles', 'neighbours', 'front_name', 'arena_name', 'attackers', 'competitors']
                }
                # # logger.debug province
                # create(Province, province, params)

                province_id = province.pop('province_id')
                province, _ = Province.objects.update_or_create(province_id=province_id, defaults=province)
                province.active_battles = extra_data['active_battles']
            page_no += 1
        logger.debug("Imported provinces for front %s done, count %s", front['front_id'], province_count)

    logger.debug("Adding province neighbours")
    for province in Province.objects.filter(province_id__in=province_dict.keys()):
        neighbours = Province.objects.filter(province_id__in=province_dict[province.province_id])
        for neighbour in neighbours:
            province.neighbours.add(neighbour)
    logger.debug("Adding province neighbours done")


if __name__ == '__main__':
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wot_clan_battles.settings")
    django.setup()

    from wgdb.models.encyclopedia import Arena
    from wgdb.models.globalmap import Season, Front, Province
    from wgdb.models.wgn import Clan, Player
    from django.conf import settings

    wot = settings.WOT['ru']
    wgn = settings.WGN['ru']

    parser = argparse.ArgumentParser("Import date from WG servers")
    parser.add_argument('--clans', dest='import_clan', action='store_true', default=False)
    parser.add_argument('--users', dest='import_user', action='store_true', default=False)
    args = parser.parse_args()

    if args.import_clan:
        sync_clans()
    if args.import_user:
        sync_users()

    sync()
