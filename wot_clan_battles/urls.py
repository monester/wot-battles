"""wot_clan_battles URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

from global_map.views import ListBattles, ListBattlesJson, TagView

urlpatterns = [
    url(r'^$', ListBattles.as_view()),
    url(r'^(?P<clan_id>\d+)/$', ListBattles.as_view()),
    url(r'^(?P<clan_tag>[A-Z0-9_\-]{2,5})/$', ListBattles.as_view()),
    url(r'^tag/', TagView.as_view()),
    url(r'^battles/$', ListBattlesJson.as_view()),
    url(r'^battles/(?P<date>\d{4}-\d{2}-\d{2})/$', ListBattlesJson.as_view()),
    url(r'^admin/', admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
