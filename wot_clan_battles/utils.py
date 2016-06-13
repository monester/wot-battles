from datetime import datetime, timedelta
import re
import pytz

region_day_begins = {
    'ru': dict(hour=3, minute=0, second=0)  # 6 am MSK time
}


def get_today(region='ru'):
    now = datetime.utcnow()
    if now.replace(**region_day_begins[region]) > now:
        today = datetime.date(now)
    else:
        today = datetime.date(now - timedelta(days=1))
    return today


def get_date(string):
    if string is None:
        return None
    if re.match("\d{4}-\d{2}-\d{2}", string[:10]):
        return datetime.strptime(string[:10], "%Y-%m-%d").replace(tzinfo=pytz.UTC)
    return string


def get_datetime(string):
    if string is None:
        return None
    dt = None
    if re.match("\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", string):
        dt = datetime.strptime(string, "%Y-%m-%dT%H:%M:%S")
    elif re.match("\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", string):
        dt = datetime.strptime(string, "%Y-%m-%d %H:%M:%S")
    if dt:
        return dt.replace(tzinfo=pytz.UTC)
    return string
