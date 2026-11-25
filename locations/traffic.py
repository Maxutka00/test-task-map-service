import logging
from django.conf import settings
from django.db import connection
from django.utils.crypto import salted_hmac
from redis import Redis
from redis.exceptions import RedisError

from .models import LocationView

logger = logging.getLogger(__name__)

redis = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)

ip_has_capacity = redis.register_script("""
local now = redis.call('TIME')
local millis = now[1] * 1000 + math.floor(now[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', millis - 3600000)
if redis.call('ZCARD', KEYS[1]) >= 50 then
    return 0
end
return 1
""")

# Перевіряємо інтервал у годину окремо для пари сесія+локація (KEYS[1]),
# а через KEYS[2] обмежуємо кількість гостьових переглядів до 50 на годину з одного IP.
admit_guest = redis.register_script("""
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0
end
local now = redis.call('TIME')
local millis = now[1] * 1000 + math.floor(now[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', millis - 3600000)
if redis.call('ZCARD', KEYS[2]) >= 50 then
    return 0
end
redis.call('SET', KEYS[1], 1, 'PX', 3600000)
redis.call('ZADD', KEYS[2], millis, ARGV[1])
redis.call('PEXPIRE', KEYS[2], 3600000)
return 1
""")


def record_view(request, location):
    prefix = f"{connection.settings_dict['NAME']}:views:{location.pk}"
    try:
        if request.user.is_authenticated:
            key = f"{prefix}:user:{request.user.pk}"
            accepted = bool(redis.set(key, 1, nx=True, ex=3600))
        else:
            address = request.META.get("REMOTE_ADDR") or "unknown"
            ip_hash = salted_hmac("guest-ip", address).hexdigest()
            ip_key = f"{prefix}:ip:{ip_hash}"

            if not request.session.session_key:
                if not ip_has_capacity(keys=[ip_key]):
                    return False
                request.session.create()
                request.session.modified = True

            guest_hash = salted_hmac("guest-session", request.session.session_key).hexdigest()
            guest_key = f"{prefix}:guest:{guest_hash}"
            accepted = bool(admit_guest(keys=[guest_key, ip_key], args=[guest_hash]))
    except RedisError:
        logger.warning("Skipping view tracking for location %s: Redis unavailable", location.pk)
        return False

    if accepted:
        LocationView.objects.create(
            location=location,
            is_guest=not request.user.is_authenticated,
        )
        return True
    return False
