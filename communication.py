import atexit
from datetime import datetime, timedelta, timezone
import os
import logging
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel


class GroupChatScrapper:
    def __init__(self, telegram_api_id, telegram_api_hash):
        self.logger = logging.getLogger("CSB")
        session_string = os.environ.get("TELEGRAM_SESSION_STRING")
        session = StringSession(session_string) if session_string else "CSB"
        self.client = TelegramClient(session, api_id=telegram_api_id, api_hash=telegram_api_hash)
        self.client.start()
        atexit.register(self.client.disconnect)

    @staticmethod
    def get_telegram_user_name(sender):
        if type(sender) is User:
            if sender.first_name and sender.last_name:
                return sender.first_name + " " + sender.last_name
            elif sender.first_name:
                return sender.first_name
            elif sender.last_name:
                return sender.last_name
            else:
                return "<unknown>"
        else:
            if type(sender) is Channel:
                return sender.title

    def get_oldest_message_date(self, chat_id):
        msg = next(self.client.iter_messages(chat_id, reverse=True), None)
        return msg.date if msg else None

    def get_message_history(self, chat_id, lookback_period, date_to=None):
        history = []
        if date_to is None:
            date_to = datetime.now(timezone.utc)
        datetime_from = date_to - timedelta(seconds=lookback_period)
        # Warning: this probably won't work with private group chats as those require joining beforehand
        # (public chats can be scrapped right away)
        for message in self.client.iter_messages(chat_id, offset_date=date_to):
            if message.date < datetime_from:
                break
            if not message.text:
                logging.warning("Non-text message skipped, summarization result might be affected")
                continue
            sender = message.get_sender()
            data = {
                "id": message.id,
                "datetime": str(message.date),
                "text": message.text,
                "sender_user_name": self.get_telegram_user_name(sender),
                "sender_user_id": sender.id,
                "is_reply": message.is_reply
            }
            if message.is_reply:
                data["reply_to_message_id"] = message.reply_to.reply_to_msg_id
            history.append(data)
        entity = self.client.get_entity(chat_id)
        chat_title = entity.title
        if entity.username:
            chat_link_base = f"https://t.me/{entity.username}"
        else:
            # Private group — use t.me/c/ID format, stripping the -100 prefix
            chat_link_base = f"https://t.me/c/{entity.id}"
        return list(reversed(history)), chat_title, chat_link_base

    def send_to_channel(self, channel_id, text):
        self.client.send_message(channel_id, text, parse_mode='html')
