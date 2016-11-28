from datetime import datetime, timedelta, date as datetime_date
import logging

from django.views.generic import TemplateView, View
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, QueryDict
from django.db.models import Count, Q

import wargaming
from global_map.models import Clan, ProvinceTag, ProvinceAssault

logger = logging.getLogger(__name__)
wot = wargaming.WoT(settings.WARGAMING_KEY, language='ru', region='ru')
wgn = wargaming.WGN(settings.WARGAMING_KEY, language='ru', region='ru')


class TagView(View):
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(TagView, self).dispatch(request, *args, **kwargs)

    def post(self, *args, **kwargs):
        province_id = self.request.POST.get('province_id')
        tag = self.request.POST.get('tag')
        date = self.request.POST.get('date')
        ProvinceTag.objects.create(date=date, province_id=province_id, tag=tag)
        return JsonResponse({'ok': 'ok'})

    def delete(self, *args, **kwargs):
        body = QueryDict(self.request.body)
        province_id = body.get('province_id')
        tag = body.get('tag')
        date = body.get('date')
        ProvinceTag.objects.filter(date=date, tag=tag,
                                   province_id=province_id).delete()
        return JsonResponse({'ok': 'ok'})


class ListBattles(TemplateView):
    template_name = 'list_battles.html'
    cached_time = None

    def get_context_data(self, **kwargs):
        context = super(ListBattles, self).get_context_data(**kwargs)
        if 'clan_tag' in kwargs:
            try:
                context['clan_id'] = Clan.objects.get_or_create(tag=kwargs['clan_tag'])[0].pk
            except Clan.MultipleObjectsReturned:
                duplicates = Clan.objects.filter(tag=kwargs['clan_tag'])
                logger.critical('Returned multiple records for same clan tag %s: IDs: %s. Forcing to update',
                                kwargs['clan_tag'], [c for c in duplicates],
                                exc_info=True)
                for c in duplicates:
                    c.force_update()
                context['clan_id'] = Clan.objects.get_or_create(tag=kwargs['clan_tag'])[0].pk
        else:
            context['clan_id'] = kwargs.get('clan_id', '35039')
        return context


class ListBattlesJson(View):
    def get(self, *args, **kwargs):
        date = kwargs.get('date')
        clan = Clan.objects.get(pk=int(self.request.GET.get('clan_id', 35039)))
        force_update = self.request.GET.get('force_update') == 'true'

        if force_update:
            from global_map.management.commands.fetchdata import update_clan
            update_clan(clan.id)

        pa_query = ProvinceAssault.objects.distinct('province').order_by('province')
        if date:
            date = datetime_date(*[int(i) for i in date.split('-')])
            assaults = [
                assault.as_clan_json(clan, current_only=False)
                for assault in pa_query.filter(date=date).filter(Q(battles__clan_a=clan) | Q(battles__clan_b=clan))
            ]
        else:
            date = datetime.now().date()
            assaults = [
                assault.as_clan_json(clan)
                for assault in pa_query.filter(date=date).filter(Q(clans=clan) | Q(current_owner=clan))
            ]

        # Remove assaults without battles
        for assault in assaults[::]:
            if not assault['battles']:
                logger.debug("Removing assault on province %s", assault['province_info']['province_id'])
                assaults.remove(assault)

        times = [
            battle['planned_start_at']
            for assault in assaults
            for battle in assault['battles']
        ]

        if times:
            min_time = min(times)
            min_time = min_time.replace(minute=min_time.minute - min_time.minute % 30)
            max_time = max(times)
        else:
            min_time = datetime.now().replace(hour=15, minute=00)
            max_time = datetime.now().replace(hour=2, minute=00) + timedelta(days=1)

        return JsonResponse({
            'time_range': [min_time, max_time],
            'assaults': sorted(
                assaults,
                key=lambda v: (v['province_info']['prime_time'].minute == 15, v['battles'][0]['planned_start_at'],
                               v['province_info']['province_id'])
            ),
        })
