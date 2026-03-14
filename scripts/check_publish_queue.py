import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.config.settings import get_settings
from src.models.base import AsyncSessionLocal
from src.models.candidate_post import CandidatePost
from src.models.publish_job import PublishJob


async def main():
    settings = get_settings()
    tz_name = settings.telegram_daily_summary_timezone
    target_tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz=UTC).astimezone(target_tz)
    
    print(f"Current Time ({tz_name}): {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 70)
    
    async with AsyncSessionLocal() as session:
        # Get posts that are 'approved' but not yet scheduled by PublishWorker
        approved_stmt = select(CandidatePost).where(CandidatePost.status == 'approved')
        approved_posts = (await session.scalars(approved_stmt)).all()
        
        # Get jobs that are 'scheduled' with their target execution time
        scheduled_stmt = select(PublishJob).where(PublishJob.status == 'scheduled').order_by(PublishJob.scheduled_for)
        scheduled_jobs = (await session.scalars(scheduled_stmt)).all()
        
        if not approved_posts and not scheduled_jobs:
            print("✨ The publish queue is currently empty.")
        else:
            if approved_posts:
                print(f"📋 [APPROVED: Awaiting Scheduling] (Total: {len(approved_posts)}):")
                print("-" * 70)
                for post in approved_posts:
                    print(f" 🔹 Source URL: {post.source_url}")
                print("\n")
            
            if scheduled_jobs:
                print(f"⏰ [SCHEDULED: Awaiting Publish Time] (Total: {len(scheduled_jobs)}):")
                print("-" * 70)
                for job in scheduled_jobs:
                    post = await session.get(CandidatePost, job.candidate_post_id)
                    job_time = job.scheduled_for.astimezone(target_tz)
                    wait_time = job_time - now_local
                    
                    if wait_time.total_seconds() > 0:
                        hours, remainder = divmod(wait_time.total_seconds(), 3600)
                        minutes, _ = divmod(remainder, 60)
                        wait_str = f"in {int(hours)}h {int(minutes)}m"
                    else:
                        wait_str = "time reached, expected to publish next cycle"
                        
                    print(f" 🔹 Expected Publish Time: {job_time.strftime('%Y-%m-%d %H:%M:%S')} ({wait_str})")
                    print(f"    Source URL: {post.source_url if post else 'Unknown'}\n")

if __name__ == "__main__":
    asyncio.run(main())
