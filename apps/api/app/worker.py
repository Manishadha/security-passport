from rq import Worker
from app.core.queue import get_queue, get_redis

def main() -> None:
    q = get_queue()
    w = Worker([q], connection=get_redis())
    w.work(with_scheduler=False)

if __name__ == "__main__":
    main()
