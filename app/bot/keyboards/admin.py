from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def build_url_keyboard(*, text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    url=url,
                )
            ]
        ]
    )


def build_web_app_keyboard(*, text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def build_admin_dashboard_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    return build_web_app_keyboard(text="Открыть админ-дашборд", url=mini_app_url)


def build_player_dashboard_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    return build_web_app_keyboard(text="Открыть дашборд свиньи", url=mini_app_url)
