# apps/api/app/cli/run_periodic_scheduler.py
from app.jobs.periodic_scheduler import run_periodic_scheduler

if __name__ == "__main__":
    res = run_periodic_scheduler(actor_user_id=None)
    print(res)