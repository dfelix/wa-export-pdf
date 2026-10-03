"""User-interface strings and date formatting, per export language.

Only labels drawn by WhatsApp's UI live here (date chips, "Edited", file
type captions...). Message content is never translated.
"""

from __future__ import annotations

from datetime import date, datetime

_MONTHS = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "edited": "Edited",
        "deleted_in": "This message was deleted",
        "deleted_out": "You deleted this message",
        "photo": "Photo",
        "video": "Video",
        "gif": "GIF",
        "sticker": "Sticker",
        "audio": "Audio",
        "voice": "Voice message",
        "document": "Document",
        "contact": "Contact",
        "location": "Location",
        "poll": "POLL",
        "poll_hint": "Select one or more",
        "votes": "votes",
        "vote": "vote",
        "view_votes": "View votes",
        "pages": "pages",
        "page": "page",
        "message_contact": "Message",
        "missing_file": "File not included in the export",
        "media_omitted": "Media omitted from export",
        "unreadable": "File could not be read",
        "view_once": "View once",
        "call_missed-voice": "Missed voice call",
        "call_missed-video": "Missed video call",
        "call_voice": "Voice call",
        "call_video": "Video call",
        "you": "You",
        "participants": "participants",
        "open_map": "Open in maps",
    },
    "pt": {
        "edited": "Editada",
        "deleted_in": "Esta mensagem foi eliminada",
        "deleted_out": "Eliminou esta mensagem",
        "photo": "Fotografia",
        "video": "Vídeo",
        "gif": "GIF",
        "sticker": "Autocolante",
        "audio": "Áudio",
        "voice": "Mensagem de voz",
        "document": "Documento",
        "contact": "Contacto",
        "location": "Localização",
        "poll": "SONDAGEM",
        "poll_hint": "Selecione uma ou mais opções",
        "votes": "votos",
        "vote": "voto",
        "view_votes": "Ver votos",
        "pages": "páginas",
        "page": "página",
        "message_contact": "Mensagem",
        "missing_file": "Ficheiro não incluído na exportação",
        "media_omitted": "Multimédia omitido na exportação",
        "unreadable": "Não foi possível ler o ficheiro",
        "view_once": "Visualização única",
        "call_missed-voice": "Chamada de voz perdida",
        "call_missed-video": "Chamada de vídeo perdida",
        "call_voice": "Chamada de voz",
        "call_video": "Chamada de vídeo",
        "you": "Você",
        "participants": "participantes",
        "open_map": "Abrir no mapa",
    },
    "pt-BR": {
        "deleted_in": "Mensagem apagada",
        "deleted_out": "Você apagou esta mensagem",
        "photo": "Foto",
        "sticker": "Figurinha",
        "contact": "Contato",
        "poll": "ENQUETE",
        "poll_hint": "Selecione uma ou mais opções",
        "missing_file": "Arquivo não incluído na exportação",
        "media_omitted": "Mídia oculta na exportação",
        "unreadable": "Não foi possível ler o arquivo",
        "call_missed-voice": "Chamada de voz perdida",
    },
    "es": {
        "edited": "Editado",
        "deleted_in": "Se eliminó este mensaje",
        "deleted_out": "Eliminaste este mensaje",
        "photo": "Foto",
        "video": "Video",
        "sticker": "Sticker",
        "audio": "Audio",
        "voice": "Mensaje de voz",
        "document": "Documento",
        "contact": "Contacto",
        "location": "Ubicación",
        "poll": "ENCUESTA",
        "poll_hint": "Selecciona una o más opciones",
        "votes": "votos",
        "vote": "voto",
        "view_votes": "Ver votos",
        "pages": "páginas",
        "page": "página",
        "message_contact": "Mensaje",
        "missing_file": "Archivo no incluido en la exportación",
        "media_omitted": "Multimedia omitido",
        "unreadable": "No se pudo leer el archivo",
        "view_once": "Ver una vez",
        "call_missed-voice": "Llamada perdida",
        "call_missed-video": "Videollamada perdida",
        "call_voice": "Llamada de voz",
        "call_video": "Videollamada",
        "you": "Tú",
        "participants": "participantes",
        "open_map": "Abrir en mapas",
    },
    "fr": {
        "edited": "Modifié",
        "deleted_in": "Ce message a été supprimé",
        "deleted_out": "Vous avez supprimé ce message",
        "photo": "Photo",
        "document": "Document",
        "contact": "Contact",
        "location": "Position",
        "votes": "votes",
        "pages": "pages",
        "missing_file": "Fichier absent de l'export",
        "you": "Vous",
    },
    "de": {
        "edited": "Bearbeitet",
        "deleted_in": "Diese Nachricht wurde gelöscht",
        "deleted_out": "Du hast diese Nachricht gelöscht",
        "photo": "Foto",
        "document": "Dokument",
        "contact": "Kontakt",
        "location": "Standort",
        "votes": "Stimmen",
        "pages": "Seiten",
        "missing_file": "Datei nicht im Export enthalten",
        "you": "Du",
    },
    "it": {
        "edited": "Modificato",
        "deleted_in": "Questo messaggio è stato eliminato",
        "deleted_out": "Hai eliminato questo messaggio",
        "photo": "Foto",
        "document": "Documento",
        "contact": "Contatto",
        "location": "Posizione",
        "votes": "voti",
        "pages": "pagine",
        "missing_file": "File non incluso nell'esportazione",
        "you": "Tu",
    },
}


class Translator:
    def __init__(self, locale: str):
        self.locale = locale if locale in _STRINGS else locale.split("-")[0]
        if self.locale not in _STRINGS:
            self.locale = "en"
        self.base = self.locale.split("-")[0]
        chain = [_STRINGS["en"]]
        if self.base in _STRINGS and self.base != "en":
            chain.append(_STRINGS[self.base])
        if self.locale != self.base:
            chain.append(_STRINGS[self.locale])
        self.strings: dict[str, str] = {}
        for table in chain:
            self.strings.update(table)

    def __call__(self, key: str) -> str:
        return self.strings.get(key, key)

    def long_date(self, d: date) -> str:
        months = _MONTHS.get(self.base, _MONTHS["en"])
        month = months[d.month - 1]
        if self.base in ("pt", "es"):
            return f"{d.day} de {month} de {d.year}"
        if self.base == "en":
            return f"{month} {d.day}, {d.year}"
        if self.base == "de":
            return f"{d.day}. {month} {d.year}"
        return f"{d.day} {month} {d.year}"

    def month_year(self, d: date) -> str:
        months = _MONTHS.get(self.base, _MONTHS["en"])
        month = months[d.month - 1]
        if self.base in ("pt", "es"):
            return f"{month.capitalize()} de {d.year}"
        return f"{month.capitalize()} {d.year}"

    @staticmethod
    def time(ts: datetime, twelve_hour: bool) -> str:
        if not twelve_hour:
            return ts.strftime("%H:%M")
        hour = ts.hour % 12 or 12
        suffix = "AM" if ts.hour < 12 else "PM"
        return f"{hour}:{ts.minute:02d} {suffix}"
