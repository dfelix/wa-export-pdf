"""Known variations of the WhatsApp ``.txt`` export format.

WhatsApp localises everything in the export: date order, 12/24h clock,
attachment markers, system messages, "media omitted" placeholders...
This module collects the patterns observed on Android and iOS exports so the
parser itself stays format-agnostic. Adding support for a new language is
mostly a matter of extending the tables below.
"""

from __future__ import annotations

import re

from ..models import MessageType

# Invisible direction marks WhatsApp sprinkles in exports (LRM, RLM, ...).
BIDI_MARKS = "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"
# Spaces that appear between time and AM/PM (narrow no-break space, etc.).
_SP = r"[    ]"

_DATE = r"(?P<date>\d{1,4}[./\-]\d{1,2}[./\-]\d{1,4})"
_AMPM = (
    r"(?P<ampm>[AaPp]\.?" + _SP + r"?[Mm]\.?"
    r"|午前|午後|上午|下午|오전|오후|ص|م)"
)
_TIME = r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?)(?:" + _SP + r"?" + _AMPM + r")?"

# Android:  15/09/26, 10:32 - Name: text
#           9/15/26, 10:32 AM - Name: text
#           2026-09-15 10:32 - Name: text
ANDROID_HEADER = re.compile(
    r"^[" + BIDI_MARKS + r"]*" + _DATE + r",?" + _SP + r"+(?:às" + _SP + r"+|um" + _SP + r"+)?"
    + _TIME + _SP + r"+[-–]" + _SP + r"+(?P<rest>.*)$"
)
# iOS:      [15/09/26, 10:32:05] Name: text
IOS_HEADER = re.compile(
    r"^[" + BIDI_MARKS + r"]*\[" + _DATE + r",?" + _SP + r"+" + _TIME + r"\]" + _SP + r"*(?P<rest>.*)$"
)

HEADER_PATTERNS = (ANDROID_HEADER, IOS_HEADER)

SENDER_SPLIT = re.compile(r"^(?P<sender>[^\n]{1,120}?):" + _SP + r"(?P<text>.*)$", re.S)
# iOS puts the body on the same line even when empty ("Name: ").
SENDER_SPLIT_EMPTY = re.compile(r"^(?P<sender>[^\n:]{1,120}):$")

# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------

_ATTACHED_ANDROID = [
    "ficheiro anexado",      # pt-PT
    "arquivo anexado",       # pt-BR
    "file attached",         # en
    "archivo adjunto",       # es
    "fichier joint",         # fr
    "Datei angehängt",       # de
    "file allegato",         # it
    "bestand bijgevoegd",    # nl
    "dosya ekli",            # tr
    "plik załączony",        # pl
    "файл прикреплен",       # ru
    "файл прикріплено",      # uk
]
ANDROID_ATTACHMENT = re.compile(
    r"^(?P<file>[^\n]+?)" + _SP + r"\((?:" + "|".join(map(re.escape, _ATTACHED_ANDROID)) + r")\)$",
    re.I,
)

_ATTACHED_IOS = [
    "attached", "anexado", "anexo", "adjunto", "pièce jointe", "Anhang",
    "allegato", "bijlage", "ek", "załącznik", "вложение", "вкладення",
]
IOS_ATTACHMENT = re.compile(
    r"^<(?:" + "|".join(map(re.escape, _ATTACHED_IOS)) + r")" + _SP + r"?:" + _SP + r"*(?P<file>[^<>\n]+)>$",
    re.I,
)

# "<Media omitted>" style placeholders (export made without media).
MEDIA_OMITTED: dict[str, MessageType] = {
    "<media omitted>": MessageType.UNKNOWN,
    "<multimédia omitido>": MessageType.UNKNOWN,
    "<multimedia omitido>": MessageType.UNKNOWN,
    "<mídia oculta>": MessageType.UNKNOWN,
    "<médias omis>": MessageType.UNKNOWN,
    "<medien ausgeschlossen>": MessageType.UNKNOWN,
    "<media omessi>": MessageType.UNKNOWN,
    "<media weggelaten>": MessageType.UNKNOWN,
    # iOS
    "image omitted": MessageType.IMAGE,
    "photo omitted": MessageType.IMAGE,
    "video omitted": MessageType.VIDEO,
    "audio omitted": MessageType.VOICE,
    "sticker omitted": MessageType.STICKER,
    "gif omitted": MessageType.GIF,
    "document omitted": MessageType.DOCUMENT,
    "contact card omitted": MessageType.CONTACT,
    "imagem ocultada": MessageType.IMAGE,
    "imagem omitida": MessageType.IMAGE,
    "vídeo ocultado": MessageType.VIDEO,
    "vídeo omitido": MessageType.VIDEO,
    "áudio ocultado": MessageType.VOICE,
    "áudio omitido": MessageType.VOICE,
    "figurinha omitida": MessageType.STICKER,
    "sticker omitido": MessageType.STICKER,
    "gif omitido": MessageType.GIF,
    "documento omitido": MessageType.DOCUMENT,
    "imagen omitida": MessageType.IMAGE,
    "video omitido": MessageType.VIDEO,
    "audio omitido": MessageType.VOICE,
    "image absente": MessageType.IMAGE,
    "vidéo absente": MessageType.VIDEO,
    "bild weggelassen": MessageType.IMAGE,
    "video weggelassen": MessageType.VIDEO,
    "immagine omessa": MessageType.IMAGE,
    "video omesso": MessageType.VIDEO,
}

VIEW_ONCE_MARKERS = {
    "<ficheiro não revelado>",
    "<arquivo não revelado>",
    "<view once message omitted>",
    "<view once voice message omitted>",
    "<file not revealed>",
    "<archivo no revelado>",
}

DELETED_MARKERS = {
    "this message was deleted",
    "you deleted this message",
    "esta mensagem foi apagada",
    "apagou esta mensagem",
    "esta mensagem foi eliminada",
    "eliminou esta mensagem",
    "mensagem apagada",
    "você apagou esta mensagem",
    "se eliminó este mensaje",
    "eliminaste este mensaje",
    "este mensaje fue eliminado",
    "ce message a été supprimé",
    "vous avez supprimé ce message",
    "diese nachricht wurde gelöscht",
    "du hast diese nachricht gelöscht",
    "questo messaggio è stato eliminato",
    "hai eliminato questo messaggio",
}

EDITED_SUFFIX = re.compile(
    r"\s*<(?:This message was edited|Esta mensagem foi editada|Mensagem editada|"
    r"Se editó este mensaje\.?|Ce message a été modifié|Diese Nachricht wurde bearbeitet|"
    r"Questo messaggio è stato modificato|Dit bericht is bewerkt)>\s*$",
    re.I,
)

LOCATION = re.compile(
    r"^(?:(?:location|localização|localizacao|ubicación|ubicacion|position|standort|posizione|locatie)"
    + _SP + r"?:" + _SP + r"*)?"
    r"(?P<url>https?://(?:maps\.google\.[a-z.]+/\S*?[?&]q=|www\.google\.[a-z.]+/maps/\S*?@|maps\.apple\.com/\S*?[?&](?:q|ll)=)"
    r"(?P<lat>-?\d+(?:\.\d+)?),(?P<lon>-?\d+(?:\.\d+)?)\S*)$",
    re.I,
)

POLL_HEADER = re.compile(r"^(?:POLL|SONDAGEM|ENQUETE|ENCUESTA|SONDAGE|UMFRAGE|SONDAGGIO|PEILING):\s*$", re.I)
POLL_OPTION = re.compile(
    r"^(?:OPTION|OPÇÃO|OPCAO|OPCIÓN|OPCION|OPTION|OPTION|OPZIONE|OPTIE):\s*(?P<text>.*?)"
    r"(?:\s*\((?P<votes>\d+)\s*(?:votes?|votos?|voix|Stimmen?|voti?|stemmen?)\))?\s*$",
    re.I,
)

CALL_MARKERS: dict[str, str] = {
    "missed voice call": "missed-voice",
    "missed video call": "missed-video",
    "missed group voice call": "missed-voice",
    "missed group video call": "missed-video",
    "chamada de voz perdida": "missed-voice",
    "chamada de vídeo perdida": "missed-video",
    "chamada de voz não atendida": "missed-voice",
    "chamada de vídeo não atendida": "missed-video",
    "llamada perdida": "missed-voice",
    "videollamada perdida": "missed-video",
    "appel vocal manqué": "missed-voice",
    "appel vidéo manqué": "missed-video",
    "verpasster sprachanruf": "missed-voice",
    "verpasster videoanruf": "missed-video",
    "chiamata vocale persa": "missed-voice",
    "videochiamata persa": "missed-video",
    "voice call": "voice",
    "video call": "video",
    "chamada de voz": "voice",
    "chamada de vídeo": "video",
}

# --------------------------------------------------------------------------
# System messages (no sender, or iOS "group name: ‎text")
# --------------------------------------------------------------------------

SYSTEM_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"end-to-end encrypted",
        r"encriptadas ponto a ponto",
        r"criptografadas de ponta a ponta",
        r"cifrados de extremo a extremo",
        r"chiffrés de bout en bout",
        r"Ende-zu-Ende-verschlüsselt",
        r"crittografia end-to-end",
        r"\b(created group|criou o grupo|criou este grupo|creó el grupo|a créé le groupe|hat die Gruppe .* erstellt|ha creato il gruppo)\b",
        r"\b(added|adicionou|añadió|a ajouté|hat .* hinzugefügt|ha aggiunto)\b",
        r"\b(removed|removeu|eliminó a|a retiré|hat .* entfernt|ha rimosso)\b",
        r"^(?:\S+(?: \S+){0,4}) (left|saiu|salió|est parti|hat die Gruppe verlassen|è uscito)$",
        r"\b(changed the subject|mudou o assunto|alterou o assunto|mudou o nome|alterou o nome|cambió el asunto|a modifié le sujet|hat den Betreff|ha cambiato l'oggetto)\b",
        r"\b(changed this group's icon|changed the group icon|mudou a imagem|alterou a imagem|alterou a fotografia|mudou a foto|cambió el ícono|a changé l'icône|hat das Gruppenbild|ha cambiato l'immagine)\b",
        r"\b(deleted this group's icon|apagou a imagem|eliminou a imagem)\b",
        r"\b(changed the group description|alterou a descrição|mudou a descrição|cambió la descripción)\b",
        r"\b(joined using this group's invite link|entrou usando o link|entrou através da ligação|se unió usando)\b",
        r"\b(security code (with .* )?changed|código de segurança|código de seguridad|code de sécurité|Sicherheitsnummer)\b",
        r"\b(changed their phone number|changed to|mudou o número|alterou o número|cambió su número)\b",
        r"\b(is now an admin|é agora administrador|agora é admin|ahora es admin)\b",
        r"\b(turned on disappearing messages|turned off disappearing messages|ativou as mensagens temporárias|desativou as mensagens temporárias|mensagens temporárias)\b",
        r"\b(pinned a message|fixou uma mensagem|afixou uma mensagem)\b",
        r"\b(blocked this contact|unblocked this contact|bloqueou este contacto|desbloqueou este contacto|bloqueou este contato|desbloqueou este contato)\b",
        r"\b(This chat is with a business account|Esta conversa é com uma conta comercial)\b",
        r"\b(You're now an admin|Agora é administrador)\b",
        r"\b(changed the settings|alterou as definições|alterou as configurações)\b",
    )
]

# --------------------------------------------------------------------------
# Locale detection
# --------------------------------------------------------------------------

LOCALE_SIGNATURES: dict[str, list[str]] = {
    "pt": ["ficheiro anexado", "Multimédia omitido", "encriptadas ponto a ponto",
           "Esta mensagem foi editada", "Esta mensagem foi apagada", "Conversa no WhatsApp com"],
    "pt-BR": ["arquivo anexado", "Mídia oculta", "criptografadas de ponta a ponta",
              "Conversa do WhatsApp com"],
    "en": ["file attached", "Media omitted", "end-to-end encrypted", "This message was deleted",
           "WhatsApp Chat with", "<attached:", "image omitted"],
    "es": ["archivo adjunto", "Multimedia omitido", "cifrados de extremo a extremo",
           "Chat de WhatsApp con", "Se eliminó este mensaje"],
    "fr": ["fichier joint", "Médias omis", "chiffrés de bout en bout", "Discussion WhatsApp avec"],
    "de": ["Datei angehängt", "Medien ausgeschlossen", "Ende-zu-Ende-verschlüsselt", "WhatsApp-Chat mit"],
    "it": ["file allegato", "Media omessi", "crittografia end-to-end", "Chat WhatsApp con"],
}

# File names WhatsApp gives to the exported text file / folder.
TITLE_PREFIXES = [
    re.compile(r"^Conversa no WhatsApp com (?P<name>.+)$", re.I),
    re.compile(r"^Conversa do WhatsApp com (?P<name>.+)$", re.I),
    re.compile(r"^WhatsApp Chat (?:with|-) (?P<name>.+)$", re.I),
    re.compile(r"^Chat de WhatsApp con (?P<name>.+)$", re.I),
    re.compile(r"^Discussion WhatsApp avec (?P<name>.+)$", re.I),
    re.compile(r"^WhatsApp[- ]Chat mit (?P<name>.+)$", re.I),
    re.compile(r"^Chat WhatsApp con (?P<name>.+)$", re.I),
    re.compile(r"^WhatsApp-chat met (?P<name>.+)$", re.I),
]


def strip_bidi(text: str) -> str:
    return text.strip(BIDI_MARKS)


def title_from_filename(stem: str) -> str | None:
    """'Conversa no WhatsApp com Ana' -> 'Ana' (None when not recognised)."""
    stem = strip_bidi(stem.strip())
    for pattern in TITLE_PREFIXES:
        m = pattern.match(stem)
        if m:
            return m.group("name").strip()
    return None
