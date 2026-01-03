#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import datetime as _dt
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

INVESTITION_URL = "https://ronson.pl/inwestycja/grunwald-miedzy-drzewami/"
INVESTITION_URL_WITH_HASH = INVESTITION_URL + "#znajdz-mieszkanie"
AJAX_MORE_URL = INVESTITION_URL + "?ajax_part=1&offset_more=7"

REPORT_DATE = _dt.date(2026, 1, 3)
REPORT_PATH = f"analiza_mieszkan_poznan_ronson_grunwald_{REPORT_DATE.isoformat()}_gpt52.md"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


@dataclasses.dataclass
class Unit:
    code: str
    term: str | None = None
    investment_name: str | None = None

    area_m2: float | None = None
    rooms: int | None = None
    floor_label: str | None = None

    status: str | None = None  # Dostępne / Rezerwacja / Sprzedane / brak danych

    price_pln: float | None = None
    price_per_m2_pln: float | None = None

    details_url: str | None = None
    building: str | None = None

    score_0_10: float | None = None


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    return r.text


def _parse_pl_number(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[^0-9,\.\s]", "", s)
    s = s.replace(" ", "")
    if not s:
        return None
    # Prefer comma as decimal separator if present
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    # Handle rare cases like 11.761,30
    if s.count(".") > 1 and "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_unit_from_card(card: Any) -> Unit | None:
    text = card.get_text(" | ", strip=True).replace("\u00a0", " ")

    code_candidates = re.findall(r"\b[A-Z]\d{1,3}\b", text)
    code_candidates = [c for c in code_candidates if not c.startswith("Q")]
    if not code_candidates:
        return None
    code = code_candidates[0]

    classes = set(card.get("class", []) or [])

    status: str | None
    if "item-apartment--sold" in classes or "Sprzedane" in text:
        status = "Sprzedane"
    elif "item-apartment--reservation" in classes or "Rezerwacja" in text:
        status = "Rezerwacja"
    elif "item-apartment--available" in classes:
        status = "Dostępne"
    else:
        status = "brak danych"

    # term like Q4’2026
    m_term = re.search(r"\bQ\d[’']\d{4}\b", text)
    term = m_term.group(0) if m_term else None

    # area like 61.02 m2 (HTML often splits 'm' and '2')
    m_area = re.search(r"(\d{1,3}[\.,]\d{2})\s*m", text)
    area_m2 = _parse_pl_number(m_area.group(1)) if m_area else None

    m_rooms = re.search(r"\b(\d+)\s*pokoj", text)
    rooms = int(m_rooms.group(1)) if m_rooms else None

    m_floor = re.search(r"\bparter\b|\b\d+\s*piętro\b", text)
    floor_label = m_floor.group(0) if m_floor else None

    m_price = re.search(r"([0-9\s\u00a0]+,[0-9]{2})\s*zł", text)
    price_pln = _parse_pl_number(m_price.group(1)) if m_price else None

    m_ppm2 = re.search(r"([0-9\s\u00a0]+,[0-9]{2})\s*zł/m", text)
    price_per_m2_pln = _parse_pl_number(m_ppm2.group(1)) if m_ppm2 else None

    a = card.select_one('a[href*="/mieszkanie/"]')
    details_url = a.get("href") if a else None

    # Investment name is usually present but we keep it optional
    inv_name = "Grunwald Między Drzewami" if "Grunwald Między Drzewami" in text else None

    return Unit(
        code=code,
        term=term,
        investment_name=inv_name,
        area_m2=area_m2,
        rooms=rooms,
        floor_label=floor_label,
        status=status,
        price_pln=price_pln,
        price_per_m2_pln=price_per_m2_pln,
        details_url=details_url,
    )


def _parse_cards(html: str) -> list[Unit]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".item-apartment:not(.item-apartment--see-more)")
    units: list[Unit] = []
    for card in cards:
        u = _extract_unit_from_card(card)
        if u:
            units.append(u)
    return units


def _merge_units(units: list[Unit]) -> list[Unit]:
    by_code: dict[str, Unit] = {}
    for u in units:
        if u.code not in by_code:
            by_code[u.code] = u
            continue
        existing = by_code[u.code]

        # Prefer entries with details URL and/or price
        if (not existing.details_url) and u.details_url:
            existing.details_url = u.details_url
        if existing.status == "brak danych" and u.status != "brak danych":
            existing.status = u.status
        if existing.term is None and u.term is not None:
            existing.term = u.term
        if existing.area_m2 is None and u.area_m2 is not None:
            existing.area_m2 = u.area_m2
        if existing.rooms is None and u.rooms is not None:
            existing.rooms = u.rooms
        if existing.floor_label is None and u.floor_label is not None:
            existing.floor_label = u.floor_label
        if existing.price_pln is None and u.price_pln is not None:
            existing.price_pln = u.price_pln
        if existing.price_per_m2_pln is None and u.price_per_m2_pln is not None:
            existing.price_per_m2_pln = u.price_per_m2_pln

    return sorted(by_code.values(), key=lambda x: x.code)


def _parse_details(unit: Unit) -> None:
    if not unit.details_url:
        return

    html = _get(unit.details_url)
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1")
    if h1:
        # e.g. "Mieszkanie nr A003 Budynek 1"
        m = re.search(r"Budynek\s+(\d+)", h1.get_text(" ", strip=True))
        if m:
            unit.building = m.group(1)

    params: dict[str, str] = {}
    for dt in soup.select("dt"):
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        k = dt.get_text(" ", strip=True).strip().lower()
        v = dd.get_text(" ", strip=True).replace("\u00a0", " ")
        params[k] = v

    # Map known fields
    if "metraż" in params:
        m_area = re.search(r"(\d{1,3}[\.,]\d{2})", params["metraż"])
        if m_area:
            unit.area_m2 = _parse_pl_number(m_area.group(1))

    if "pokoje" in params:
        m_rooms = re.search(r"\b(\d+)\b", params["pokoje"])
        if m_rooms:
            unit.rooms = int(m_rooms.group(1))

    if "piętro" in params:
        unit.floor_label = params["piętro"]

    if "status" in params:
        v = params["status"].strip()
        if v:
            unit.status = v

    if "termin realizacji" in params:
        unit.term = params["termin realizacji"].strip() or unit.term

    if "cena" in params:
        v = params["cena"]
        m_price = re.search(r"([0-9\s\u00a0]+,[0-9]{2})\s*zł", v)
        if m_price:
            unit.price_pln = _parse_pl_number(m_price.group(1))
        m_ppm2 = re.search(r"([0-9\s\u00a0]+,[0-9]{2})\s*zł/m", v)
        if m_ppm2:
            unit.price_per_m2_pln = _parse_pl_number(m_ppm2.group(1))


def _floor_score(floor_label: str | None) -> float:
    if not floor_label:
        return 0.0
    floor_label = floor_label.strip().lower()
    if "parter" in floor_label:
        return 0.4
    m = re.search(r"(\d+)", floor_label)
    if not m:
        return 0.0
    f = int(m.group(1))
    if f == 1:
        return 0.8
    if f == 2:
        return 1.0
    if f == 3:
        return 0.8
    if f == 4:
        return 0.6
    return 0.4


def _area_score(area_m2: float | None, rooms: int | None) -> float:
    if area_m2 is None or rooms is None:
        return 0.0
    target = 62.0 if rooms == 3 else 78.0 if rooms == 4 else 0.0
    if target == 0.0:
        return 0.0
    # 0..1, linear penalty up to 20 m2 away
    return max(0.0, 1.0 - abs(area_m2 - target) / 20.0)


def _compute_scores(units: list[Unit]) -> None:
    ppm2_values = [
        u.price_per_m2_pln
        for u in units
        if u.price_per_m2_pln is not None
        and u.rooms in (3, 4)
        and (u.status or "").lower() in ("dostępne", "rezerwacja")
    ]

    ppm2_min = min(ppm2_values) if ppm2_values else None
    ppm2_max = max(ppm2_values) if ppm2_values else None

    def price_score(ppm2: float | None) -> float:
        if ppm2 is None or ppm2_min is None or ppm2_max is None:
            return 0.0
        if ppm2_max == ppm2_min:
            return 1.5
        # 0..3: lower price/m2 => higher score
        return 3.0 * (ppm2_max - ppm2) / (ppm2_max - ppm2_min)

    for u in units:
        rooms_component = 3.0 if u.rooms in (3, 4) else 0.0

        st = (u.status or "").strip().lower()
        if st == "dostępne":
            status_component = 2.0
        elif st == "rezerwacja":
            status_component = 1.0
        else:
            status_component = 0.0

        u.score_0_10 = round(
            rooms_component
            + status_component
            + price_score(u.price_per_m2_pln)
            + _floor_score(u.floor_label)
            + _area_score(u.area_m2, u.rooms),
            2,
        )


def _fmt_pln(v: float | None) -> str:
    if v is None:
        return "brak danych"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return s + " zł"


def _fmt_pln_int(v: float | None) -> str:
    if v is None:
        return "brak danych"
    s = f"{v:,.0f}".replace(",", " ")
    return s + " zł"


def _fmt_ppm2(v: float | None) -> str:
    if v is None:
        return "brak danych"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return s + " zł/m²"


def _fmt_m2(v: float | None) -> str:
    if v is None:
        return "brak danych"
    return f"{v:.2f} m²"


def _build_report(units: list[Unit]) -> str:
    total = len(units)
    count_available = sum(1 for u in units if (u.status or "").lower() == "dostępne")
    count_reserved = sum(1 for u in units if (u.status or "").lower() == "rezerwacja")
    count_sold = sum(1 for u in units if (u.status or "").lower() == "sprzedane")
    with_details = sum(1 for u in units if u.details_url)

    candidates = [
        u
        for u in units
        if u.rooms in (3, 4) and (u.status or "").lower() in ("dostępne", "rezerwacja")
    ]
    candidates_sorted = sorted(
        candidates,
        key=lambda u: (-(u.score_0_10 or 0.0), u.price_pln if u.price_pln is not None else 10**18),
    )
    top3 = candidates_sorted[:3]

    lines: list[str] = []
    lines.append(f"# Analiza inwestycji Ronson \"Grunwald Między Drzewami\" — Poznań (pełna lista lokali)")
    lines.append("")
    lines.append(f"> Data analizy: {REPORT_DATE.isoformat()}")
    lines.append(f"> Źródło: {INVESTITION_URL_WITH_HASH}")
    lines.append("> Uwaga: nie zgaduję brakujących danych — oznaczam jako `brak danych`.")
    lines.append("")

    # Budżet: repo-wide default; mark as assumption
    lines.append("## 1) Założenia i twarde kryteria")
    lines.append("- Twardy wymóg: **3–4 pokoje** (inne lokale oznaczam jako odrzucone).")
    lines.append("- Budżet all-in: **900 000 PLN** (założenie zgodne z wcześniejszymi raportami w repo — jeśli masz inny, zmień i przelicz).")
    lines.append("- Rynek: pierwotny (deweloper) — PCC zwykle 0% (ale koszty notarialne/opłaty i dodatki nadal dochodzą).")
    lines.append("")

    lines.append("## 2) Zasięg danych (co realnie da się wyciągnąć ze strony)")
    lines.append(f"- Łącznie kafelków (deklarowane na stronie): 211; zebrane: **{total}**")
    lines.append(f"- Statusy: Dostępne **{count_available}**, Rezerwacja **{count_reserved}**, Sprzedane **{count_sold}**, inne/brak danych **{total - count_available - count_reserved - count_sold}**")
    lines.append(f"- Podstrony szczegółów (`/mieszkanie/...`): **{with_details}** (pozostałe pozycje na liście często nie mają publicznej karty szczegółów — wtedy zakres danych jest uboższy)")
    lines.append("")

    lines.append("## 3) TOP 3 (tylko 3–4 pokoje + Dostępne/Rezerwacja)")
    if not top3:
        lines.append("Brak kandydatów spełniających twardy wymóg 3–4 pokoje (wg danych dostępnych na stronie).")
    else:
        for i, u in enumerate(top3, 1):
            lines.append(
                f"- #{i}: **{u.code}** — {_fmt_m2(u.area_m2)}, {u.rooms} pokoje, {u.floor_label or 'brak danych'}, {u.status or 'brak danych'}, cena {_fmt_pln_int(u.price_pln)}, {_fmt_ppm2(u.price_per_m2_pln)}, score **{u.score_0_10:.2f}/10**{(' — ' + u.details_url) if u.details_url else ''}"
            )
    lines.append("")

    lines.append("## 4) Tabela porównawcza (wymagana) — wszystkie lokale z listy")
    lines.append(
        "| Kod | Pokoje | Metraż | Piętro | Termin | Status | Cena | Cena/m² | Score 0–10 | Link |")
    lines.append(
        "|---|---:|---:|---|---|---|---:|---:|---:|---|")

    for u in units:
        rejected = " (odrzucone: ≠3–4 pokoje)" if (u.rooms is not None and u.rooms not in (3, 4)) else ""
        status = (u.status or "brak danych") + rejected
        link = u.details_url or ""
        score = f"{u.score_0_10:.2f}" if u.score_0_10 is not None else "brak danych"
        lines.append(
            f"| {u.code} | {u.rooms if u.rooms is not None else 'brak danych'} | {_fmt_m2(u.area_m2)} | {u.floor_label or 'brak danych'} | {u.term or 'brak danych'} | {status} | {_fmt_pln_int(u.price_pln)} | {_fmt_ppm2(u.price_per_m2_pln)} | {score} | {link} |"
        )

    lines.append("")
    lines.append("## 5) Krytyczne uwagi / red flags (na podstawie danych ze strony)")
    lines.append("- Dla większości lokali brak publicznie podanych: ekspozycji, informacji o windzie, czynszu/zaliczkach, standardzie wykończenia, cenie i dostępności miejsc postojowych oraz komórek.")
    lines.append("- Same statusy ‘Sprzedane’ w tabeli nie dają wglądu w historyczne ceny (na stronie są osobne pliki ‘Historia zmian cen’ — warto je pobrać i przeanalizować osobno).")
    lines.append("- Bez danych o parkingu/komórce i kosztach stałych nie da się rzetelnie policzyć ‘all-in’ dla każdego lokalu — tu wymagane są doprecyzowania od doradcy.")
    lines.append("")

    lines.append("## 6) Pytania do sprzedającego (lista kontrolna)")
    lines.append("- Czy **zakup miejsca postojowego** jest obligatoryjny dla wybranego lokalu? Jeśli tak: cena, typ (hala/naziemne), osobna KW?")
    lines.append("- Cena i dostępność **komórki lokatorskiej/schowka** (czy obowiązkowe/zalecane)?")
    lines.append("- **Winda**: czy jest, ile, czy dojeżdża do hali garażowej?")
    lines.append("- **Ekspozycja okien** (strony świata) i czy lokal jest jednostronny/dwustronny.")
    lines.append("- **Dokładny układ** (rzut), wymiary sypialni, możliwość wydzielenia kuchni / zmian lokatorskich.")
    lines.append("- **Opłaty miesięczne** (czynsz administracyjny/zaliczki) — szacunek dla 3–4 os.")
    lines.append("- **Standard deweloperski** (specyfikacja): okna, drzwi, instalacje, wentylacja, przygotowanie pod klimę.")
    lines.append("- Harmonogram płatności, rachunek powierniczy, warunki odstąpienia, terminy odbioru i kary za opóźnienia.")
    lines.append("")

    lines.append("## 7) Checklista na oględziny / odbiór")
    lines.append("- Hałas: ekspozycja na ulicę/torowisko, okna otwarte, godziny szczytu.")
    lines.append("- Parter: prywatność, przechodnie, ryzyko włamania, wilgoć; ogródek — ogrodzenie i utrzymanie.")
    lines.append("- Ostatnie piętra: przegrzewanie, izolacja dachu, serwis i gwarancje.")
    lines.append("- Logistyka: wózek, rower, komórka, winda do hali.")
    lines.append("- Odbiór techniczny: piony, wentylacja, wilgotność, spadki, stolarka, akustyka.")

    return "\n".join(lines) + "\n"


def main() -> None:
    print("[1/4] Pobieram listę lokali (pierwsze 7 + część AJAX)…")
    initial_html = _get(INVESTITION_URL_WITH_HASH)
    more_html = _get(AJAX_MORE_URL)

    initial_units = _parse_cards(initial_html)
    more_units = _parse_cards(more_html)

    units = _merge_units(initial_units + more_units)
    print(f"Zebrane lokale: {len(units)} (initial={len(initial_units)}, ajax_more={len(more_units)})")

    print("[2/4] Dociągam szczegóły dla lokali z publiczną kartą…")
    detail_units = [u for u in units if u.details_url]
    for i, u in enumerate(detail_units, 1):
        if i % 20 == 0:
            print(f"  …{i}/{len(detail_units)}")
        try:
            _parse_details(u)
        except Exception as e:
            print(f"  WARN: nie udało się pobrać szczegółów {u.code}: {e}")
        time.sleep(0.15)

    print("[3/4] Liczę scoring…")
    _compute_scores(units)

    print("[4/4] Generuję raport Markdown…")
    report = _build_report(units)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"OK: zapisano {REPORT_PATH}")


if __name__ == "__main__":
    main()
