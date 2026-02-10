from redis import Redis
from rq import Queue
from app.core.settings import settings

def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)

def get_queue() -> Queue:
    return Queue("default", connection=get_redis())
