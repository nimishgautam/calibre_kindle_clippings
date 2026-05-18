from __future__ import annotations

import datetime as _datetime
import re
from typing import Optional

from .models import BookAnnotations, ParseIssue, ParsedClipping
from .text import normalize_text


_LANG_AND_KIND_DETECT_BY_START_WORDS = {
    "Your Highlight": ("en", "highlight"),
    "Your Note": ("en", "note"),
    "Your Bookmark": ("en", "bookmark"),
    "Highlight": ("en", "highlight"),
    "Note": ("en", "note"),
    "Bookmark": ("en", "bookmark"),
    "Ihre Markierung": ("de", "highlight"),
    "Ihre Notiz": ("de", "note"),
    "Ihr Lesezeichen": ("de", "bookmark"),
    "Markierung": ("de", "highlight"),
    "Notiz": ("de", "note"),
    "Lesezeichen": ("de", "bookmark"),
    "La subrayado": ("es", "highlight"),
    "La nota": ("es", "note"),
    "La marcador": ("es", "bookmark"),
    "Mi subrayado": ("es", "highlight"),
    "Mi nota": ("es", "note"),
    "Mi marcador": ("es", "bookmark"),
    "Tu subrayado": ("es", "highlight"),
    "Tu nota": ("es", "note"),
    "Tu marcador": ("es", "bookmark"),
    "Votre surlignement": ("fr", "highlight"),
    "Votre note": ("fr", "note"),
    "Votre signet": ("fr", "bookmark"),
    "La mia evidenziazione": ("it", "highlight"),
    "Le mie note": ("it", "note"),
    "Il mio segnalibro": ("it", "bookmark"),
    "La tua evidenziazione": ("it", "highlight"),
    "La tua nota": ("it", "note"),
    "Il tuo segnalibro": ("it", "bookmark"),
    "ハイライト": ("jp", "highlight"),
    "メモ": ("jp", "note"),
    "ブックマーク": ("jp", "bookmark"),
    "Seu destaque": ("pt", "highlight"),
    "Sua nota": ("pt", "note"),
    "Seu marcador": ("pt", "bookmark"),
    "我的标注": ("ch", "highlight"),
    "我的笔记": ("ch", "note"),
    "我的书签": ("ch", "bookmark"),
}

_LOCATION_REGEX = {
    "en": (r"\sLocation\s*%s", r"\slocation\s*%s", r"\sLoc\.\s*%s"),
    "de": (r"\sPosition\s*%s", r"\sPos\.\s*%s"),
    "es": (r"\sPosición\s*%s", r"\sposición\s*%s"),
    "fr": (r"\sEmplacement\s*%s",),
    "it": (r"\sPosizione\s*%s", r"\sposizione\s*%s"),
    "jp": (r"\s位置No.\s*%s",),
    "pt": (r"\sPosição\s*%s", r"\sposição\s*%s"),
    "ch": (r"\s位置\s*%s",),
}

_PAGE_REGEX = {
    "en": (r"\sPage\s*%s", r"\spage\s*%s"),
    "de": (r"\sSeite\s*%s",),
    "es": (r"\spágina\s*%s",),
    "fr": (r"\spage\s*%s",),
    "it": (r"\spagina\s*%s",),
    "jp": (r"\sジ\s*%s",),
    "pt": (r"\spágina\s*%s",),
    "ch": (r"\s第\s*%s\s*页",),
}

_MONTH_NAMES = {
    "en": {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    },
    "de": {
        "Januar": 1,
        "Jänner": 1,
        "Februar": 2,
        "März": 3,
        "April": 4,
        "Mai": 5,
        "Juni": 6,
        "Juli": 7,
        "August": 8,
        "September": 9,
        "Oktober": 10,
        "November": 11,
        "Dezember": 12,
    },
    "es": {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    },
    "fr": {
        "janvier": 1,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "décembre": 12,
    },
    "it": {
        "gennaio": 1,
        "febbraio": 2,
        "marzo": 3,
        "aprile": 4,
        "maggio": 5,
        "giugno": 6,
        "luglio": 7,
        "agosto": 8,
        "settembre": 9,
        "ottobre": 10,
        "novembre": 11,
        "dicembre": 12,
    },
    "pt": {
        "janeiro": 1,
        "fevereiro": 2,
        "março": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    },
}

_MONTH_NAMES_SHORT = {
    "en": {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12},
    "de": {"Jan": 1, "Jän": 1, "Feb": 2, "Mrz": 3, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12},
    "es": {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12},
    "fr": {"janv.": 1, "févr.": 2, "mars": 3, "avr.": 4, "mai": 5, "juin": 6, "juil.": 7, "août": 8, "sept.": 9, "oct.": 10, "nov.": 11, "déc.": 12},
    "it": {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12},
    "pt": {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12},
}


def parse_file(path: str) -> tuple[list[ParsedClipping], list[ParseIssue]]:
    with open(path, "rb") as handle:
        return parse_bytes(handle.read())


def parse_bytes(raw: bytes) -> tuple[list[ParsedClipping], list[ParseIssue]]:
    issues: list[ParseIssue] = []
    text = raw.decode("utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return [], issues
    if not text.endswith("\n"):
        text += "\n"

    records = re.split(r"^==========\n", text, flags=re.MULTILINE)
    if records and records[-1].strip() == "":
        records.pop()
    else:
        issues.append(ParseIssue("error", "Invalid end of clippings file"))

    clippings: list[ParsedClipping] = []
    for record in records:
        record = record.encode().decode("utf-8-sig")
        match = re.match(r"\s*(\S[^\n]*)\n-\s+([^\n|]+\|[^\n]+)\n\s*\n(.*)\n$", record, re.DOTALL)
        if not match:
            if clippings:
                issues.append(ParseIssue("warning", "Joined malformed record to previous clipping text", record))
                clippings[-1].text = f"{clippings[-1].text}\n=========={record}"
            else:
                issues.append(ParseIssue("error", "Invalid start of clippings file", record))
            continue

        bookline, statusline, body = match.groups()
        title, author = _get_title_and_author(bookline.strip())
        split_idx = statusline.rindex("|")
        language, kind = _detect_language_and_type(statusline[:split_idx])
        if not kind or not language:
            issues.append(ParseIssue("error", f"Could not detect clipping type: {statusline}", record))
            continue

        begin, end, page = _get_location(statusline[:split_idx], language)
        created_at = _get_datetime(statusline[split_idx + 1 :], language)
        if created_at is None:
            issues.append(ParseIssue("warning", f"Could not parse clipping timestamp: {statusline}", record))

        clippings.append(
            ParsedClipping(
                order=len(clippings),
                bookline=bookline,
                title=title,
                author=author,
                statusline=statusline,
                language=language,
                kind=kind,
                text=body,
                created_at=created_at,
                begin=begin,
                end=end,
                page=page,
            )
        )
    return clippings, issues


def group_clippings(clippings: list[ParsedClipping]) -> list[BookAnnotations]:
    grouped: dict[str, BookAnnotations] = {}
    for clipping in clippings:
        key = f"{normalize_text(clipping.title)}|{normalize_text(clipping.author)}"
        if key not in grouped:
            grouped[key] = BookAnnotations(key=key, title=clipping.title, author=clipping.author)
        grouped[key].clippings.append(clipping)
    return list(grouped.values())


def _detect_language_and_type(status: str) -> tuple[Optional[str], Optional[str]]:
    words = status.split(None, 3)
    for count in range(1, 4):
        key = " ".join(words[:count])
        if key in _LANG_AND_KIND_DETECT_BY_START_WORDS:
            return _LANG_AND_KIND_DETECT_BY_START_WORDS[key]
    return None, None


def _get_location(status: str, language: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    begin = end = page = None
    for regex in _LOCATION_REGEX[language]:
        pattern = regex % r"([0-9][0-9,.-]*[0-9]|[0-9])"
        matches = re.findall(pattern, status, flags=re.IGNORECASE)
        if matches and len(matches) == 1:
            location = re.sub(r"[,.]", "", matches[0], flags=re.IGNORECASE)
            if "-" in location:
                left, right = re.match(r"([0-9]+)-([0-9]+)", location).groups()
                begin = int(left)
                end = int(left[: -len(right)] + right)
            else:
                begin = end = int(location)
            status = re.sub(pattern, " ", status, flags=re.IGNORECASE)
            break

    for regex in _PAGE_REGEX[language]:
        pattern = regex % r"([0-9][0-9,.]*[0-9]|[0-9])"
        matches = re.findall(pattern, status, flags=re.IGNORECASE)
        if matches and len(matches) == 1:
            page = int(re.sub(r"[,.]", "", matches[0], flags=re.IGNORECASE))
            status = re.sub(pattern, " ", status, flags=re.IGNORECASE)
            break

    if (not begin and page) or (begin and not page):
        numbers = re.findall(r"[0-9]+", status, flags=re.IGNORECASE)
        if len(numbers) == 1:
            if not begin:
                begin = end = int(numbers[0])
            else:
                page = int(numbers[0])
    return begin, end, page


def _get_datetime(status: str, language: str) -> Optional[_datetime.datetime]:
    year = month = day = hour = minute = second = micro = 0
    date_time_re = r"([0-2]?[0-9])[.:]([0-5][0-9])(?::([0-5][0-9])(?:\.([0-9]+))?)?\s*([AP]\.?M|Uhr)?\s*(?:[A-Z]{3}?([+-][0-2]?[0-9](?::[0-5][0-9])?))?"
    match = re.search(date_time_re, status, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if match.lastindex and match.lastindex >= 3 and match.group(3):
            second = int(match.group(3))
        if match.lastindex and match.lastindex >= 4 and match.group(4):
            micro = int(1000000.0 * float("0." + match.group(4)))
        if match.lastindex and match.lastindex >= 5 and match.group(5) and match.group(5).upper().replace(".", "") == "PM" and hour < 12:
            hour += 12
        status = re.sub(date_time_re, " ", status, flags=re.IGNORECASE)

    if language in ("jp", "ch"):
        day_match = re.search(r"([0-9]+)\s?日", status)
        month_match = re.search(r"([0-9]+)\s?月", status)
        year_match = re.search(r"([0-9]+)\s?年", status)
        if day_match:
            day = int(day_match.group(1))
        if month_match:
            month = int(month_match.group(1))
        if year_match:
            year = int(year_match.group(1))
    else:
        words = re.split(r"[,;]?\s", status)
        month = _find_month(language, words)
        if month:
            numbers = [int(n) for n in re.findall(r"[0-9]+", status)]
            if len(numbers) == 2 and min(numbers) <= 31:
                if numbers[0] > 31:
                    day, year = numbers[1], numbers[0]
                else:
                    day, year = numbers[0], numbers[1]
                if year < 100:
                    year += 2000

    if day and month and year:
        return _datetime.datetime(year, month, day, hour, minute, second, micro)
    return None


def _find_month(language: str, words: list[str]) -> int:
    for word in words:
        if word in _MONTH_NAMES.get(language, {}):
            return _MONTH_NAMES[language][word]
    for word in words:
        if word in _MONTH_NAMES_SHORT.get(language, {}):
            return _MONTH_NAMES_SHORT[language][word]
    for word in words:
        lower = word.lower()
        if lower in _MONTH_NAMES.get(language, {}):
            return _MONTH_NAMES[language][lower]
        if lower in _MONTH_NAMES_SHORT.get(language, {}):
            return _MONTH_NAMES_SHORT[language][lower]
    return 0


def _get_title_and_author(line: str) -> tuple[str, Optional[str]]:
    title = None
    author = None
    if line.endswith(")"):
        idx = line.rindex("(")
        while idx >= 0 and line[idx:].count("(") != line[idx:].count(")"):
            idx = line.rindex("(", 0, idx - 1) if idx > 0 else -1
        if idx > 0:
            title = line[:idx].strip()
            author = line[idx + 1 : -1].strip()
    if title is None:
        title = line
    return title, author
