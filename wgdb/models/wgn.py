from django.db import models
# from simple_history.models import HistoricalRecords


class Clan(models.Model):
    clan_id = models.IntegerField(primary_key=True)
    tag = models.CharField(max_length=5, null=True)
    title = models.CharField(max_length=255, null=True)
    description = models.TextField(null=True)

    # history = HistoricalRecords()

    class Meta:
        index_together = [
            ["clan_id", ],
            ["tag", ],
        ]


class Player(models.Model):
    account_id = models.IntegerField()
    created_at = models.DateTimeField(null=True)
    nickname = models.CharField(max_length=255, null=True)
    clan = models.ForeignKey(Clan, null=True)

    # history = HistoricalRecords()

    class Meta:
        index_together = [
            ["account_id", ],
            ["nickname", ],
            ["clan"],
        ]


class Game(models.Model):
    player = models.ManyToManyField(Player, related_name='games')
    game = models.CharField(max_length=255)
