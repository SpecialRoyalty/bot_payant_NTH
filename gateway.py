"""Adaptateur Telegram : isole le moteur testable du SDK et de son réseau."""

from telegram import ChatPermissions, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

import engine


class TelegramGateway:
    def __init__(self, bot):
        self.bot = bot

    @property
    def id(self):
        return self.bot.id

    async def call(self, method, *args, **kwargs):
        if isinstance(kwargs.get("reply_markup"), dict):
            kwargs["reply_markup"] = InlineKeyboardMarkup.de_json(kwargs["reply_markup"], self.bot)
        if isinstance(kwargs.get("permissions"), dict):
            kwargs["permissions"] = ChatPermissions.de_json(kwargs["permissions"], self.bot)
        try:
            return await getattr(self.bot, method)(*args, **kwargs)
        except RetryAfter as error:
            raise engine.RetryAfter(error.retry_after) from error
        except Forbidden as error:
            raise engine.Forbidden(str(error)) from error
        except BadRequest as error:
            raise engine.BadRequest(str(error)) from error
        except TelegramError as error:
            raise engine.TelegramError(type(error).__name__) from error

    async def send_photo(self, **kwargs):
        return await self.call("send_photo", **kwargs)

    async def send_message(self, **kwargs):
        return await self.call("send_message", **kwargs)

    async def delete_message(self, **kwargs):
        return await self.call("delete_message", **kwargs)

    async def get_chat(self, chat_id):
        return await self.call("get_chat", chat_id)

    async def get_chat_member(self, chat_id, user_id):
        return await self.call("get_chat_member", chat_id, user_id)

    async def set_chat_permissions(self, **kwargs):
        return await self.call("set_chat_permissions", **kwargs)
