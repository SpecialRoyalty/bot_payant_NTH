"""État durable et automatisations. Les appels sont sérialisés par engine.lock."""

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
AD_INTERVAL = 6 * 60 * 60
CLOSED_PERMISSIONS = {
    "can_send_messages": False,
    "can_send_audios": False,
    "can_send_documents": False,
    "can_send_photos": False,
    "can_send_videos": False,
    "can_send_video_notes": False,
    "can_send_voice_notes": False,
    "can_send_polls": False,
    "can_send_other_messages": False,
    "can_add_web_page_previews": False,
    "can_react_to_messages": False,
    "can_edit_tag": False,
    "can_change_info": False,
    "can_invite_users": False,
    "can_pin_messages": False,
    "can_manage_topics": False,
}


class TelegramError(Exception):
    """Erreur réseau/API neutralisée par le transport."""


class BadRequest(TelegramError):
    pass


class Forbidden(TelegramError):
    pass


class RetryAfter(TelegramError):
    def __init__(self, retry_after):
        super().__init__("Limite de débit Telegram")
        self.retry_after = retry_after


def utc_now():
    return datetime.now(timezone.utc)


def parse_admin_ids(value):
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not re.fullmatch(r"[1-9][0-9]*", p) for p in parts):
        raise ValueError("ADMIN_IDS doit contenir des IDs numériques positifs séparés par des virgules.")
    return frozenset(int(part) for part in parts)


def has_admin_access(user_id, chat_type, admin_ids):
    return user_id in admin_ids and chat_type == "private"


def normalize_username(value):
    value = value.strip()
    value = re.sub(r"^(?:https?://)?(?:www\.)?t\.me/", "", value, flags=re.I)
    value = value.removeprefix("@").rstrip("/")
    # Les pseudos de collection peuvent être plus courts que cinq caractères.
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", value):
        raise ValueError("Envoyez un @pseudo Telegram ou un lien https://t.me/pseudo, sans paramètres.")
    return value


def validate_caption(value):
    value = value.strip()
    if not value or len(value.encode("utf-16-le")) // 2 > 1024:
        raise ValueError("Le texte doit faire de 1 à 1 024 caractères (certains emojis comptent pour deux).")
    return value


def opening_slot(now):
    """Retourne le créneau local fermé et son compte à rebours, sinon None."""
    local = now.astimezone(PARIS)
    if not 1 <= local.hour < 21:
        return None
    # Compte à rebours basé sur l'heure murale de Paris : 01 h → 20 h, 11 h → 10 h.
    remaining = 21 - local.hour
    return f"{local.date().isoformat()}T{local.hour:02d}", remaining


def countdown_text(hours):
    suffix = "heure" if hours == 1 else "heures"
    return f"Le groupe ouvrira dans {hours} {suffix}."


@dataclass
class State:
    group_id: int | None = None
    group_title: str = ""
    photo_id: str = ""
    text: str = ""
    vip_username: str = ""
    ad_enabled: bool = False
    next_ad_at: float = 0
    ad_message: dict | None = None
    opening_enabled: bool = False
    # Conservé pour lire sans erreur les bases créées par la version précédente.
    opening_last_date: str = ""
    opening_last_slot: str = ""
    opening_message: dict | None = None
    opening_group_closed: bool = False
    opening_saved_permissions: dict | None = None
    service_deletions: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    retry_at: dict = field(default_factory=dict)


class Store:
    """État PostgreSQL JSONB. Une connexion courte est utilisée par opération."""

    def __init__(self, database_url, connector=None):
        if not database_url:
            raise ValueError("DATABASE_URL est vide.")
        if connector is None:
            import psycopg
            connector = psycopg.connect
        self.database_url = database_url
        self.connector = connector
        with self.connector(self.database_url, connect_timeout=10) as db:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_state (
                        id SMALLINT PRIMARY KEY CHECK (id = 1),
                        value JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute("SELECT value FROM bot_state WHERE id = 1")
                row = cursor.fetchone()
        if row:
            value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            self.state = State(**value)
        else:
            self.state = State()
        self.save()

    def save(self):
        value = json.dumps(asdict(self.state), ensure_ascii=False)
        with self.connector(self.database_url, connect_timeout=10) as db:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO bot_state (id, value, updated_at)
                    VALUES (1, %s::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (value,),
                )

    def close(self):
        # Les connexions sont déjà fermées à la fin de chaque opération.
        pass


class Engine:
    def __init__(self, store, bot):
        self.store, self.bot = store, bot
        self.lock = asyncio.Lock()

    @property
    def state(self):
        return self.store.state

    def save(self):
        self.store.save()

    def ready(self):
        s = self.state
        return bool(s.group_id and s.photo_id and s.text and s.vip_username)

    def vip_button(self):
        return {"inline_keyboard": [[{"text": "VIP", "url": f"https://t.me/{self.state.vip_username}"}]]}

    def fail(self, key, error, now):
        if isinstance(error, Forbidden):
            detail = "Bot retiré, bloqué ou accès refusé : vérifiez ses droits dans le groupe."
        elif isinstance(error, BadRequest):
            detail = "Action refusée : vérifiez les droits du bot, la photo et l’âge du message (moins de 48 h)."
        else:
            detail = "Telegram indisponible : une nouvelle tentative est prévue."
        delay = 60
        if isinstance(error, RetryAfter):
            raw = error.retry_after
            delay = max(delay, raw.total_seconds() if isinstance(raw, timedelta) else raw)
        self.state.errors[key] = detail
        self.state.retry_at[key] = now.timestamp() + delay
        self.save()

    def clear_error(self, key):
        self.state.errors.pop(key, None)
        self.state.retry_at.pop(key, None)

    async def delete(self, ref, key, now):
        if not ref:
            return True
        try:
            await self.bot.delete_message(chat_id=ref["chat_id"], message_id=ref["message_id"])
        except BadRequest as error:
            if "message to delete not found" not in str(error).lower():
                self.fail(key, error, now)
                return False
        except TelegramError as error:
            self.fail(key, error, now)
            return False
        self.clear_error(key)
        return True

    async def remove_tracked(self, field_name, key, now):
        if await self.delete(getattr(self.state, field_name), key, now):
            setattr(self.state, field_name, None)
            self.save()
            return True
        return False

    async def require_group_rights(self, chat_id, admin_id):
        chat = await self.bot.get_chat(chat_id)
        if chat.type not in ("group", "supergroup"):
            raise ValueError("Choisissez un groupe Telegram.")
        admin = await self.bot.get_chat_member(chat_id, admin_id)
        if admin.status not in ("creator", "administrator"):
            raise ValueError("Vous devez aussi être administrateur du groupe choisi.")
        member = await self.bot.get_chat_member(chat_id, self.bot.id)
        if (member.status != "administrator" or not getattr(member, "can_delete_messages", False)
                or not getattr(member, "can_restrict_members", False)):
            raise ValueError(
                "Ajoutez le bot comme administrateur avec les droits « Supprimer les messages » "
                "et « Restreindre les membres »."
            )
        return chat

    async def connect(self, chat, now):
        s = self.state
        if s.group_id == chat.id:
            s.group_title = chat.title or str(chat.id)
            self.save()
            return
        # Ne jamais abandonner l'ancien groupe fermé lors d'un changement.
        s.opening_enabled = False
        self.save()
        if not await self.reconcile_opening(now):
            raise ValueError(
                "Impossible de rouvrir l’ancien groupe. Rétablissez le droit « Restreindre les membres » "
                "puis réessayez."
            )
        # Ne pas abandonner de publicité dans l'ancien groupe.
        if not await self.remove_tracked("ad_message", "publicité", now):
            raise ValueError("Impossible de supprimer l’ancienne publicité. Rétablissez les droits dans l’ancien groupe puis réessayez.")
        s.group_id, s.group_title = chat.id, chat.title or str(chat.id)
        s.ad_enabled = s.opening_enabled = False
        s.next_ad_at = 0
        s.opening_last_date = ""
        s.opening_last_slot = ""
        s.opening_group_closed = False
        s.opening_saved_permissions = None
        self.clear_error("publicité")
        self.clear_error("ouverture")
        self.save()

    async def publish_ad(self, now):
        if not self.ready():
            raise ValueError("Configurez d’abord le groupe, la photo, le texte et le @pseudo VIP.")
        s = self.state
        # En cas d'échec de suppression, garder l'ancienne et ne pas accumuler de publicités.
        if not await self.remove_tracked("ad_message", "publicité", now):
            return False
        try:
            message = await self.bot.send_photo(
                chat_id=s.group_id, photo=s.photo_id, caption=s.text, reply_markup=self.vip_button(),
            )
        except TelegramError as error:
            self.fail("publicité", error, now)
            return False
        s.ad_message = {"chat_id": s.group_id, "message_id": message.message_id}
        s.ad_enabled = True
        s.next_ad_at = now.timestamp() + AD_INTERVAL
        self.clear_error("publicité")
        self.save()
        return True

    async def pause_ads(self, now):
        self.state.ad_enabled = False
        self.save()
        return await self.remove_tracked("ad_message", "publicité", now)

    async def set_opening(self, enabled, now):
        if enabled and not self.state.group_id:
            raise ValueError("Connectez d’abord un groupe.")
        self.state.opening_enabled = enabled
        self.save()  # OFF reste enregistré même si la réouverture ou la suppression échoue.
        return await self.reconcile_opening(now)

    async def remember_permissions(self, now):
        s = self.state
        if s.opening_saved_permissions is not None:
            return True
        try:
            chat = await self.bot.get_chat(s.group_id)
            permissions = chat.permissions
            if permissions is None:
                raise BadRequest("Permissions du groupe indisponibles")
            if hasattr(permissions, "to_dict"):
                permissions = permissions.to_dict()
            s.opening_saved_permissions = dict(permissions)
            # Sauvegarder avant l'appel distant : un arrêt brutal ne perd pas l'état à restaurer.
            self.save()
            return True
        except TelegramError as error:
            self.fail("ouverture", error, now)
            return False

    async def close_group(self, now):
        s = self.state
        if s.opening_group_closed:
            return True
        if not await self.remember_permissions(now):
            return False
        try:
            await self.bot.set_chat_permissions(
                chat_id=s.group_id,
                permissions=CLOSED_PERMISSIONS,
                use_independent_chat_permissions=True,
            )
        except TelegramError as error:
            self.fail("ouverture", error, now)
            return False
        s.opening_group_closed = True
        self.clear_error("ouverture")
        self.save()
        return True

    async def open_group(self, now):
        s = self.state
        if not s.opening_group_closed:
            return True
        if s.opening_saved_permissions is None:
            self.fail("ouverture", BadRequest("Permissions à restaurer indisponibles"), now)
            return False
        try:
            await self.bot.set_chat_permissions(
                chat_id=s.group_id,
                permissions=s.opening_saved_permissions,
                use_independent_chat_permissions=True,
            )
        except TelegramError as error:
            self.fail("ouverture", error, now)
            return False
        s.opening_group_closed = False
        # À 01 h, les permissions alors en vigueur seront capturées à nouveau.
        s.opening_saved_permissions = None
        self.clear_error("ouverture")
        self.save()
        return True

    async def reconcile_opening(self, now):
        s = self.state
        slot = opening_slot(now) if s.opening_enabled and s.group_id else None

        # OFF, ou phase ouverte de 21 h à 01 h : restaurer puis effacer le compte à rebours.
        if slot is None:
            if not await self.open_group(now):
                return False
            if not await self.remove_tracked("opening_message", "ouverture", now):
                return False
            s.opening_saved_permissions = None
            if not s.opening_enabled:
                s.opening_last_slot = ""
                s.opening_last_date = ""
            self.clear_error("ouverture")
            self.save()
            return True

        if not await self.close_group(now):
            return False
        slot_id, hours = slot
        if s.opening_last_slot == slot_id and s.opening_message:
            return True
        # Toujours supprimer le message précédent avant de publier le suivant.
        if not await self.remove_tracked("opening_message", "ouverture", now):
            return False
        try:
            message = await self.bot.send_message(chat_id=s.group_id, text=countdown_text(hours))
        except TelegramError as error:
            self.fail("ouverture", error, now)
            return False
        s.opening_last_slot = slot_id
        s.opening_message = {"chat_id": s.group_id, "message_id": message.message_id}
        self.clear_error("ouverture")
        self.save()
        return True

    async def service_message(self, chat_id, message_id, now):
        if chat_id != self.state.group_id:
            return
        ref = {"chat_id": chat_id, "message_id": message_id}
        if ref not in self.state.service_deletions:
            self.state.service_deletions.append(ref)
            self.save()
        if await self.delete(ref, "entrées/sorties", now):
            self.state.service_deletions.remove(ref)
            self.save()

    def migrate(self, old_id, new_id):
        s = self.state
        if s.group_id != old_id:
            return
        s.group_id = new_id
        for ref in [s.ad_message, s.opening_message, *s.service_deletions]:
            if ref and ref["chat_id"] == old_id:
                ref["chat_id"] = new_id
        self.save()

    async def tick(self, now=None):
        now = now or utc_now()
        async with self.lock:
            s = self.state
            # Priorité à la suppression de l'annonce, indépendamment de la publicité.
            if now.timestamp() >= s.retry_at.get("ouverture", 0):
                await self.reconcile_opening(now)
            if now.timestamp() >= s.retry_at.get("publicité", 0):
                if s.ad_enabled and self.ready() and now.timestamp() >= s.next_ad_at:
                    await self.publish_ad(now)
                elif not s.ad_enabled and s.ad_message:
                    await self.remove_tracked("ad_message", "publicité", now)
            if now.timestamp() >= s.retry_at.get("entrées/sorties", 0):
                for ref in list(s.service_deletions)[:20]:
                    if not await self.delete(ref, "entrées/sorties", now):
                        break
                    s.service_deletions.remove(ref)
                    self.save()
