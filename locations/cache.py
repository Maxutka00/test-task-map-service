import logging
from hashlib import sha256
from urllib.parse import urlencode
from uuid import uuid4

from django.core.cache import cache
from django.db import connection, transaction
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

LIST_QUERY_PARAMS = (
    "page",
    "search",
    "ordering",
    "category",
    "author",
    "rating",
    "min_rating",
    "max_rating",
)


def version_key():
    return f"{connection.settings_dict['NAME']}:locations:list:version"


def _bump_version():
    try:
        cache.set(version_key(), uuid4().hex, timeout=None)
    except RedisError:
        logger.warning("Failed to bump location list cache version in Redis")


def invalidate_list():
    transaction.on_commit(_bump_version, robust=True)


def list_cache_key(request):
    version = cache.get_or_set(version_key(), lambda: uuid4().hex, timeout=None)
    filtered_params = [
        (param, request.query_params.getlist(param))
        for param in LIST_QUERY_PARAMS
        if param in request.query_params
    ]
    canonical_query = urlencode(filtered_params, doseq=True)
    raw_url = f"{request.scheme}://{request.get_host()}{request.path}?{canonical_query}"
    url_hash = sha256(raw_url.encode()).hexdigest()
    return f"{connection.settings_dict['NAME']}:locations:list:{version}:{url_hash}"


def get_cached_list(request):
    try:
        return cache.get(list_cache_key(request))
    except RedisError:
        logger.warning("Redis unavailable while reading location list cache")
        return None


def set_cached_list(request, data, timeout=60):
    try:
        cache.set(list_cache_key(request), data, timeout=timeout)
    except RedisError:
        logger.warning("Redis unavailable while writing location list cache")
