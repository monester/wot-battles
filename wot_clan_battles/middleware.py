from global_map.models import Clan


class WGUserMiddleware(object):
    @staticmethod
    def process_request(request):
        clan_id = request.session.get('user_clan_id')
        clan = Clan.objects.get_or_create(pk=int(clan_id))[0] if clan_id else None

        request.wg_user = {
            'id': request.session.get('user_id'),
            'username': request.session.get('username'),
            'clan': clan
        }
