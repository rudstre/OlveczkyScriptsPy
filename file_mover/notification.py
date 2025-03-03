import asyncio
import logging
from datetime import datetime
from configparser import ConfigParser
from pushover import init, Client

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, config: ConfigParser):
        self.app_token = config["FileMover"]["pushover_app_token"]
        self.user_key = config["FileMover"]["pushover_user_key"]
        self.selected_devices = [
            d.strip() for d in config["FileMover"]["selected_devices"].split(",") if d.strip()
        ]
        self.rate_limit = int(config["FileMover"]["notification_rate_limit"])
        self.last_notification_time = datetime.min
        init(self.app_token)
        self.client = Client(self.user_key)
        if not self.client.verify():
            logger.error("Pushover credentials verification failed")
            raise ValueError("Invalid Pushover credentials")

    async def send_notification(self, message: str, title: str = "Notification"):
        now = datetime.now()
        if (now - self.last_notification_time).total_seconds() < self.rate_limit:
            logger.info("Notification rate limited")
            return
        self.last_notification_time = now
        for device in self.selected_devices:
            try:
                await asyncio.to_thread(self.client.send_message, message, title=title, device=device)
                logger.info(f"Notification sent to {device}: {title}")
            except Exception as e:
                logger.exception(f"Failed to send notification to {device}: {e}")