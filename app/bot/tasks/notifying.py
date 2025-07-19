import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import User, Server
from app.bot.services.vpn import VPNService
from app.config import Config

logger = logging.getLogger(__name__)


async def notifying_expiring_vpn_users(
    session_factory: async_sessionmaker,
    vpn_service: VPNService,
    config: Config,
) -> None:
    async with session_factory() as session:
        stmt = select(User).where(User.server_id.isnot(None))
        result = await session.execute(stmt)
        users = result.scalars().all()

        now = datetime.now(timezone.utc)
        notified_count = 0

        for user in users:
            try:
                expiry_time = await vpn_service.get_expiry_time(user)
                if expiry_time and expiry_time != 0:
                    expiry_time = datetime.fromtimestamp(expiry_time / 1000, timezone.utc)
                    days_to_expiration = (expiry_time - now).days 
                    if days_to_expiration == config.shop.EXPIRATION_NOTIFY:
                        notify = await vpn_service.notify_client(user)
                        if notify:                            
                            user.server_id = None
                            notified_count += 1
                            logger.info(
                                f"Notified user {user.tg_id} (days to expiration {days_to_expiration:.1f} )"
                            )
            except Exception as e:
                logger.error(f"Error processing user {getattr(user, 'tg_id', user)}: {e}")

        logger.info(f"[Notification task] Notified {notified_count} expiring VPN clients.")
        

def start_scheduler(session_factory: async_sessionmaker, vpn_service: VPNService, config: Config) -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        notifying_expiring_vpn_users,
        "interval",
        hours=23,
        args=[session_factory, vpn_service, config],
        next_run_time=datetime.now(),
    )
    scheduler.start()