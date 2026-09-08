"""Bot Telegram : panneau privé à boutons, un seul groupe, accès par IDs."""

import asyncio
import logging
import os
import secrets
from contextlib import suppress
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton as Button,
    InlineKeyboardMarkup as Markup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from engine import (
    Engine, PARIS, Store, TelegramError as EngineError, has_admin_access,
    normalize_username, parse_admin_ids, parse_group_id, utc_now, validate_caption,
)
from gateway import TelegramGateway

LOG = logging.getLogger("vip_bot")


def authorized(update, admin_ids):
    return bool(update.effective_user and update.effective_chat and has_admin_access(
        update.effective_user.id, update.effective_chat.type, admin_ids,
    ))


class AdminUI:
    def __init__(self, engine, admin_ids):
        self.engine, self.admin_ids = engine, admin_ids

    async def guard(self, update):
        if authorized(update, self.admin_ids):
            return True
        if update.callback_query:
            await update.callback_query.answer("Accès réservé aux administrateurs autorisés.", show_alert=True)
        elif update.effective_chat and update.effective_chat.type == "private" and update.message:
            await update.message.reply_text(
                f"Accès réservé aux administrateurs autorisés.\nVotre ID Telegram : {update.effective_user.id}"
            )
        return False

    def menu(self):
        s = self.engine.state
        rows = [
            [Button("👥 Connecter / changer de groupe", callback_data="group")],
            [Button("🖼 Photo", callback_data="photo"), Button("📝 Texte", callback_data="text")],
            [Button("🔗 Configurer le @pseudo VIP", callback_data="vip")],
            [Button("👀 Aperçu", callback_data="preview"), Button("📢 Publier / actualiser", callback_data="publish")],
        ]
        if s.ad_enabled:
            rows.append([Button("⏸ Arrêter la publicité", callback_data="pause")])
        rows.extend([
            [Button(f"{'🟢' if s.opening_enabled else '🔴'} Ouverture : {'ON' if s.opening_enabled else 'OFF'}",
                    callback_data=f"opening:{0 if s.opening_enabled else 1}")],
            [Button("🗄 Vérifier PostgreSQL", callback_data="db_check")],
            [Button("🔄 Actualiser le panneau", callback_data="home")],
        ])
        return Markup(rows)

    def group_menu(self, bot_username):
        s = self.engine.state
        rows = [[Button(
            "➕ Ajouter le bot au groupe",
            url=f"https://t.me/{bot_username}?startgroup=connect&admin=delete_messages+restrict_members",
        )]]
        for item in s.detected_groups[:8]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                continue
            prefix = "✅" if item["id"] == s.group_id else "📍"
            title = str(item.get("title") or item["id"])
            rows.append([Button(f"{prefix} {title}"[:60], callback_data=f"group_pick:{item['id']}")])
        rows.extend([
            [Button("✍️ Ajouter avec l’ID", callback_data="manual_group")],
            [Button("👥 Sélecteur Telegram", callback_data="choose_group")],
            [Button("⬅️ Retour", callback_data="home")],
        ])
        return Markup(rows)

    def panel_text(self, notice=""):
        s = self.engine.state
        next_ad = "—"
        if s.ad_enabled and s.next_ad_at:
            from datetime import datetime
            next_ad = datetime.fromtimestamp(s.next_ad_at, PARIS).strftime("%d/%m à %H:%M")
        text = (
            "⚙️ PANNEAU ADMIN\n\n"
            f"Groupe : {s.group_title or 'non connecté'}\n"
            f"PostgreSQL : {'✅ connecté' if self.engine.store.connected else '❌ indisponible'}\n"
            f"Photo : {'✅' if s.photo_id else 'à configurer'}\n"
            f"Texte : {'✅' if s.text else 'à configurer'}\n"
            f"VIP : {'@' + s.vip_username if s.vip_username else 'à configurer'}\n\n"
            f"Publicité toutes les 6 h : {'ON' if s.ad_enabled else 'OFF'}\n"
            f"Prochaine publication : {next_ad}\n"
            f"Ouverture : {'ON' if s.opening_enabled else 'OFF'}\n"
            f"État du groupe : {'FERMÉ' if s.opening_group_closed else 'OUVERT'}\n"
            "Fermeture + compte à rebours : 01 h → 21 h\n"
            "Ouvert sans compte à rebours : 21 h → 01 h\n"
            "Horaires : Europe/Paris"
        )
        if s.errors:
            text += "\n\n⚠️ " + "\n".join(f"{k} : {v}" for k, v in s.errors.items())
        return text + (f"\n\n{notice}" if notice else "")

    async def panel(self, update, notice="", edit=False):
        if edit and update.callback_query and update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(self.panel_text(notice), reply_markup=self.menu())
                return
            except BadRequest as error:
                if "message is not modified" in str(error).lower():
                    return
                # Un ancien panneau supprimé peut être remplacé par un nouveau.
        await update.get_bot().send_message(
            chat_id=update.effective_chat.id, text=self.panel_text(notice), reply_markup=self.menu(),
        )

    async def start(self, update, context):
        if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            user = update.effective_user
            if not user or user.id not in self.admin_ids:
                return
            notice = ""
            try:
                async with self.engine.lock:
                    chat = await self.engine.require_group_rights(update.effective_chat.id, user.id)
                    await self.engine.connect(chat, utc_now())
                notice = "✅ Groupe détecté et connecté automatiquement."
            except ValueError as error:
                notice = f"⚠️ {error}"
            except (TelegramError, EngineError):
                notice = "⚠️ Telegram refuse l’accès au groupe. Vérifiez les deux droits du bot."
            except Exception as error:
                LOG.error("Connexion groupe impossible : %s", type(error).__name__)
                notice = "❌ Connexion impossible. Vérifiez PostgreSQL dans le panneau."
            with suppress(TelegramError):
                await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
            with suppress(TelegramError):
                await context.bot.send_message(
                    chat_id=user.id, text=self.panel_text(notice), reply_markup=self.menu(),
                )
            return
        if not await self.guard(update):
            return
        context.user_data.clear()
        await update.message.reply_text("Bienvenue dans votre panneau admin.", reply_markup=ReplyKeyboardRemove())
        await self.panel(update)

    async def callback(self, update, context):
        if not await self.guard(update):
            return
        query = update.callback_query
        await query.answer()
        action = query.data
        # Une autre action annule la saisie précédente pour cet administrateur.
        context.user_data.clear()
        if action == "group":
            await query.edit_message_text(
                "Ajoutez le bot comme administrateur avec les droits « Supprimer les messages » et "
                "« Restreindre les membres ». Le groupe sera détecté et connecté automatiquement.\n\n"
                "Les groupes détectés apparaissent ci-dessous. Si Telegram ne les affiche pas, utilisez "
                "« Ajouter avec l’ID » ou envoyez /start dans le groupe.\n\n"
                "Vous devez être administrateur du groupe. Changer de groupe arrête les deux automatismes.",
                reply_markup=self.group_menu(context.bot.username),
            )
            return
        if action == "choose_group":
            request_id = secrets.randbelow(2**31 - 1) + 1
            context.user_data.update(mode="group_share", request_id=request_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Appuyez sur le bouton « Sélectionner mon groupe » sous le champ de saisie.",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("👥 Sélectionner mon groupe", request_chat=KeyboardButtonRequestChat(
                        request_id=request_id, chat_is_channel=False, bot_is_member=True, request_title=True,
                    ))],
                    [KeyboardButton("⬅️ Annuler")],
                ], resize_keyboard=True, one_time_keyboard=True),
            )
            return
        if action == "manual_group":
            context.user_data["mode"] = "group_id"
            await query.edit_message_text(
                "Envoyez l’ID numérique négatif du groupe, par exemple -1001234567890.\n\n"
                "Le bot doit déjà être administrateur de ce groupe avec les deux droits requis.",
                reply_markup=Markup([[Button("⬅️ Annuler", callback_data="home")]]),
            )
            return
        prompts = {
            "photo": "Envoyez la photo de la publicité (en tant que photo Telegram).",
            "text": "Envoyez le texte de la publicité, sur plusieurs lignes si besoin (1 024 caractères maximum).",
            "vip": "Envoyez le @pseudo Telegram vers lequel le bouton VIP doit renvoyer.",
        }
        if action in prompts:
            context.user_data["mode"] = action
            await query.edit_message_text(prompts[action], reply_markup=Markup([[Button("⬅️ Annuler", callback_data="home")]]))
            return
        notice = ""
        try:
            async with self.engine.lock:
                if action == "preview":
                    s = self.engine.state
                    if not (s.photo_id and s.text and s.vip_username):
                        raise ValueError("Configurez la photo, le texte et le @pseudo VIP.")
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id, photo=s.photo_id, caption=s.text,
                        reply_markup=Markup.de_json(self.engine.vip_button(), context.bot),
                    )
                    notice = "Aperçu envoyé en privé. Vérifiez aussi la destination du bouton VIP."
                elif action == "publish":
                    ok = await self.engine.publish_ad(utc_now())
                    notice = "✅ Publicité publiée. La prochaine remplacera celle-ci dans 6 h." if ok else "⚠️ Publication impossible. Vérifiez l’erreur ci-dessus puis réessayez."
                elif action == "pause":
                    ok = await self.engine.pause_ads(utc_now())
                    notice = "Publicité arrêtée et message supprimé." if ok else "Publicité arrêtée. Suppression en attente, nouvelle tentative automatique."
                elif action in ("opening:0", "opening:1"):
                    enabled = action == "opening:1"
                    ok = await self.engine.set_opening(enabled, utc_now())
                    if enabled:
                        notice = (
                            "🟢 Cycle activé : groupe fermé de 01 h à 21 h avec compte à rebours horaire, "
                            "puis ouvert de 21 h à 01 h."
                            if ok else
                            "🟢 Cycle activé, mais la synchronisation est en attente. Vérifiez les droits du bot."
                        )
                    else:
                        notice = (
                            "🔴 Cycle désactivé : groupe ouvert et compte à rebours supprimé."
                            if ok else
                            "🔴 Cycle désactivé. Réouverture ou suppression en attente ; vérifiez les droits du bot."
                        )
                elif action.startswith("group_pick:"):
                    chat_id = parse_group_id(action.removeprefix("group_pick:"))
                    chat = await self.engine.require_group_rights(chat_id, update.effective_user.id)
                    await self.engine.connect(chat, utc_now())
                    notice = "✅ Groupe connecté depuis la liste détectée."
                elif action == "db_check":
                    await asyncio.to_thread(self.engine.store.check)
                    notice = "✅ PostgreSQL répond correctement et l’état du bot est accessible."
        except ValueError as error:
            notice = str(error)
        except (TelegramError, EngineError):
            notice = "Telegram refuse l’action ou ne répond pas. Vérifiez les droits du bot puis réessayez."
        except Exception as error:
            LOG.error("Action admin impossible : %s", type(error).__name__)
            notice = "❌ PostgreSQL ne répond pas. Vérifiez DATABASE_URL et le service Postgres sur Railway."
        await self.panel(update, notice, edit=True)

    async def receive(self, update, context):
        if not await self.guard(update):
            return
        message = update.message
        if not message:
            return
        mode = context.user_data.get("mode")
        if message.text == "⬅️ Annuler":
            context.user_data.clear()
            await message.reply_text("Saisie annulée.", reply_markup=ReplyKeyboardRemove())
            await self.panel(update)
            return
        try:
            async with self.engine.lock:
                s = self.engine.state
                if mode == "group_share":
                    shared = message.chat_shared
                    if not shared or shared.request_id != context.user_data.get("request_id"):
                        raise ValueError("Utilisez le bouton « Sélectionner mon groupe » sous le champ de saisie.")
                    chat = await self.engine.require_group_rights(shared.chat_id, update.effective_user.id)
                    await self.engine.connect(chat, utc_now())
                    notice = "✅ Groupe connecté. Configurez la publicité puis appuyez sur « Publier / actualiser »."
                elif mode == "group_id":
                    chat_id = parse_group_id(message.text or "")
                    chat = await self.engine.require_group_rights(chat_id, update.effective_user.id)
                    await self.engine.connect(chat, utc_now())
                    notice = "✅ Groupe connecté manuellement."
                elif mode == "photo":
                    if not message.photo:
                        raise ValueError("Envoyez une photo, pas un fichier ou du texte.")
                    s.photo_id = message.photo[-1].file_id
                    notice = "✅ Photo enregistrée."
                elif mode == "text":
                    s.text = validate_caption(message.text or "")
                    notice = "✅ Texte enregistré."
                elif mode == "vip":
                    s.vip_username = normalize_username(message.text or "")
                    notice = "✅ Destination VIP enregistrée. Vérifiez le lien avec « Aperçu »."
                else:
                    await self.panel(update, "Choisissez une action avec les boutons.")
                    return
                self.engine.save()
        except ValueError as error:
            await message.reply_text(str(error))
            return
        except (TelegramError, EngineError):
            await message.reply_text(
                "Impossible d’accéder au groupe. Ajoutez le bot comme admin avec les droits de supprimer "
                "les messages et de restreindre les membres, puis réessayez."
            )
            return
        except Exception as error:
            LOG.error("Enregistrement impossible : %s", type(error).__name__)
            await message.reply_text("PostgreSQL ne répond pas. Vérifiez DATABASE_URL sur Railway.")
            return
        context.user_data.clear()
        await message.reply_text(notice, reply_markup=ReplyKeyboardRemove())
        await self.panel(update)

    async def service(self, update, context):
        message = update.message
        if message and (message.new_chat_members or message.left_chat_member):
            async with self.engine.lock:
                await self.engine.service_message(message.chat_id, message.message_id, utc_now())

    async def migration(self, update, context):
        message = update.message
        async with self.engine.lock:
            if message.migrate_to_chat_id:
                self.engine.migrate(message.chat_id, message.migrate_to_chat_id)
            elif message.migrate_from_chat_id:
                self.engine.migrate(message.migrate_from_chat_id, message.chat_id)

    async def membership(self, update, context):
        event = update.my_chat_member
        if not event or event.chat.type not in ("group", "supergroup", "channel"):
            return
        after = event.new_chat_member
        is_in = after.status in ("member", "administrator", "creator") or (
            after.status == "restricted" and after.is_member
        )
        if event.chat.type == "channel":
            await context.bot.leave_chat(event.chat.id)
            return
        # Un ajout extérieur ne donne aucun contrôle. Un admin autorisé pourra ensuite
        # connecter explicitement le groupe par le panneau ou avec /start dans le groupe.
        if not is_in or event.from_user.id not in self.admin_ids:
            return
        try:
            async with self.engine.lock:
                chat = await self.engine.require_group_rights(event.chat.id, event.from_user.id)
                if not self.engine.state.group_id or self.engine.state.group_id == chat.id:
                    await self.engine.connect(chat, utc_now())
                    notice = "✅ Groupe détecté et connecté automatiquement."
                else:
                    self.engine.remember_detected_group(chat)
                    self.engine.save()
                    notice = "📍 Groupe détecté. Choisissez-le dans « Connecter / changer de groupe »."
        except ValueError as error:
            notice = f"⚠️ Groupe détecté, mais non connecté : {error}"
        except (TelegramError, EngineError):
            notice = "⚠️ Groupe détecté, mais Telegram refuse la vérification des droits."
        except Exception as error:
            LOG.error("Détection groupe impossible : %s", type(error).__name__)
            notice = "❌ Groupe détecté, mais PostgreSQL ne répond pas."
        with suppress(TelegramError):
            await context.bot.send_message(
                chat_id=event.from_user.id, text=self.panel_text(notice), reply_markup=self.menu(),
            )


def build_application(token, admin_ids, store):
    wake_scheduler = asyncio.Event()

    async def automation_loop():
        while True:
            try:
                await engine.tick()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.error("Automatisation temporairement indisponible : %s", type(error).__name__)
                wake_scheduler.clear()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wake_scheduler.wait(), timeout=60)
                continue

            next_at = engine.next_wakeup_at()
            wake_scheduler.clear()
            if next_at is None:
                await wake_scheduler.wait()
                continue
            delay = max(0.05, next_at - utc_now().timestamp())
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(wake_scheduler.wait(), timeout=delay)

    async def startup(app):
        await app.bot.set_my_commands([])
        app.bot_data["automation_task"] = asyncio.create_task(
            automation_loop(), name="automatisations",
        )
        LOG.info("PostgreSQL connecté ; table bot_state prête.")
        LOG.info("Bot démarré ; panneau disponible en privé.")

    async def error_handler(update, context):
        # Ne jamais journaliser les URL HTTP contenant le token ni les messages privés.
        LOG.error("Erreur non traitée : %s", type(context.error).__name__)

    async def stop_automations(app):
        task = app.bot_data.get("automation_task")
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def shutdown(app):
        store.close()

    app = (Application.builder().token(token).concurrent_updates(False)
           .connection_pool_size(4).get_updates_connection_pool_size(1)
           .get_updates_read_timeout(60)
           .post_init(startup).post_stop(stop_automations).post_shutdown(shutdown).build())
    engine = Engine(store, TelegramGateway(app.bot), wake_scheduler.set)
    ui = AdminUI(engine, admin_ids)
    app.bot_data["engine"] = engine
    app.add_handler(CommandHandler("start", ui.start))
    app.add_handler(CallbackQueryHandler(ui.callback))
    app.add_handler(ChatMemberHandler(ui.membership, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.MIGRATE, ui.migration))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, ui.service))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.UpdateType.EDITED_MESSAGE, ui.receive))
    app.add_error_handler(error_handler)
    return app


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "REMPLACER_PAR_LE_TOKEN_BOTFATHER" or ":" not in token:
        raise SystemExit("Renseignez BOT_TOKEN dans .env avec le token de @BotFather.")
    try:
        admin_ids = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url or database_url == "${{Postgres.DATABASE_URL}}":
        raise SystemExit(
            "Renseignez DATABASE_URL. Sur Railway, utilisez la référence ${{Postgres.DATABASE_URL}} "
            "dans les variables du service du bot."
        )
    try:
        store = Store(database_url)
    except Exception as error:
        LOG.error("Connexion PostgreSQL impossible : %s", type(error).__name__)
        raise SystemExit("Connexion PostgreSQL impossible. Vérifiez DATABASE_URL et le service Postgres.") from None
    app = build_application(token, admin_ids, store)
    app.run_polling(
        timeout=50,
        allowed_updates=["message", "callback_query", "my_chat_member"],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
