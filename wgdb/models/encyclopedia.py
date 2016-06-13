from __future__ import unicode_literals

from django.utils.encoding import python_2_unicode_compatible
from django.db import models


@python_2_unicode_compatible
class Arena(models.Model):
    arena_id = models.CharField(max_length=255, primary_key=True)
    camouflage_type = models.CharField(max_length=255)
    description = models.TextField()
    name_i18n = models.CharField(max_length=255)

    def __repr__(self):
        return "<Arena: %s>" % self.arena_id

    def __str__(self):
        return self.name_i18n
