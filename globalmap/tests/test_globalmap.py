import pytest

from globalmap.models import Province
from .fixtures import wot


def test_provinces(wot):
    with pytest.raises(Exception):
        Province()
    p = Province(province_id='1', front_id='1', region='ru')
    p.save()
