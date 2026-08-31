# -*- coding: utf-8 -*-
"""Treiber: Datenpruefung -> Rendern -> Formatkontrolle -> PDF -> Pruefbericht.

Geaendert am 21.08.2026: Der PDF-Export lief bisher INNERHALB der Befundschleife
und zusaetzlich im Schlussdurchlauf — bei drei Runden also vier Chromium-Starts,
von denen drei verworfen wurden. Er steht jetzt hinter der Schleife. Waehrend der
Runden bleibt die PDF-Pruefung ausgesetzt (`pdf_pruefen=False`), damit sie keinen
Scheinbefund erzeugt, der die Schleife am Konvergieren hindert.
"""
import json
import os
import sys
import time

import mmlib
import render as R
import build_mail as BM
import validate as V
import make_pdf as MP

HIER = os.path.dirname(os.path.abspath(__file__))


def _now():
    """UTC-Uhrzeit als String, fuer die Phasenzeitstempel (V4, 28.08.2026)."""
    return time.strftime("%H:%M:%S", time.gmtime())


def lauf():
    zeiten = {"start": _now()}

    with open(os.path.join(HIER, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    ref = mmlib.lade_referenz()
    datum = data["meta"]["datum"]

    # 1 -- Datenpruefung VOR dem Rendern
    dbef = V.datenpruefung(data, ref)
    zeiten["datenpruefung_fertig"] = _now()
    print("== Datenpruefung: %d Befund(e)" % len(dbef))
    for x in dbef:
        print("   -", x)

    rep = None
    befunde, kz = [], []
    html_pfad, mail_html, mail_text = None, None, None

    # 2 -- Befundschleife OHNE PDF
    for runde in (1, 2, 3):
        html_pfad, kenn, data = R.render(rep)
        doc_roh = open(html_pfad, encoding="utf-8").read()
        mail_html, mail_text = BM.build(
            data, rep or {"befunde": [], "kennzahlen": []}, doc_roh)
        doc = open(html_pfad, encoding="utf-8").read()
        befunde, kz = V.pruefe(doc, data, kenn, mail_html, mail_text,
                               pdf_txt=None, pdf_pruefen=False)
        alle = dbef + befunde
        gb = BM.groessenbericht(mail_html)
        print("== Runde %d: %d Befund(e), %d Links, Tier A/B %.1f %%, "
              "Mail-Body %d Bytes" % (runde, len(alle), kenn["links"],
                                      kenn["tier_quote"], gb["bytes"]))
        for x in alle:
            print("   -", x)
        neu = {"befunde": alle, "kennzahlen": kz,
               "anmerkungen": data.get("meta", {}).get("anmerkungen", [])}
        zeiten["runde_%d" % runde] = _now()
        if rep is not None and [b for b in rep["befunde"]] == alle:
            rep = neu
            break
        rep = neu

    # 3 -- Schlussdurchlauf MIT PDF
    zeiten["schlussdurchlauf_start"] = _now()
    html_pfad, kenn, data = R.render(rep)
    mail_html, mail_text = BM.build(
        data, rep, open(html_pfad, encoding="utf-8").read())
    try:
        pdf_pfad = MP.make(html_pfad, datum)
        pdf_txt = MP.pdf_text(pdf_pfad)
    except Exception as e:
        pdf_pfad, pdf_txt = None, ""
        print("!! PDF-Export fehlgeschlagen:", e)
    zeiten["pdf_fertig"] = _now()

    doc = open(html_pfad, encoding="utf-8").read()
    befunde, kz = V.pruefe(doc, data, kenn, mail_html, mail_text, pdf_txt,
                           pdf_pruefen=True, mail_bytes=len(mail_html.encode("utf-8")))
    rep = {"befunde": dbef + befunde, "kennzahlen": kz,
           "anmerkungen": data.get("meta", {}).get("anmerkungen", [])}

    seks = V.sektionstexte(doc)
    import re as _re

    def w(n):
        return mmlib.woerter(seks.get(n, ""))

    def l(n):
        return len(_re.findall(r"<a\s[^>]*href=", seks.get(n, "")))

    gb = BM.groessenbericht(mail_html)
    zus = {
        "html": html_pfad,
        "pdf": pdf_pfad,
        "pdf_woerter": len([x for x in (pdf_txt or "").split() if x.strip()]),
        "woerter_gesamt": sum(w(n) for n, _, _, _ in V.SEKTIONEN),
        "links_gesamt": len(_re.findall(r"<a\s[^>]*href=", doc)),
        "makro_woerter": w(6), "makro_links": l(6),
        "kalender_woerter": w(7), "kalender_links": l(7),
        "sektionen": {str(n): [w(n), l(n)] for n, _, _, _ in V.SEKTIONEN},
        "doppelt": kenn["doppelt"], "einfach": kenn["einfach"],
        "ungueltig": kenn["ungueltig"],
        "tier_quote": round(kenn["tier_quote"], 1),
        "quellen": kenn["quellen"],
        "mail_body": gb,
        "befunde": rep["befunde"],
        "befunde_anzahl": len(rep["befunde"]),
        "zeiten": zeiten,
    }
    zeiten["zusammenfassung_fertig"] = _now()
    with open(os.path.join(HIER, "zusammenfassung.json"), "w", encoding="utf-8") as f:
        json.dump(zus, f, ensure_ascii=False, indent=1)
    print("\n== ZUSAMMENFASSUNG ==")
    print(json.dumps(zus, ensure_ascii=False, indent=1))
    return zus


if __name__ == "__main__":
    lauf()
    sys.exit(0)
