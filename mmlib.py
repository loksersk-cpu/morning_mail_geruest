# -*- coding: utf-8 -*-
"""
mmlib.py -- Belegapparat, Platzhalteraufloesung, Tabellen, SVG-Chart, Dokumentbau.
Gehoert zum Geruest der Morning Mail. Tagesunabhaengig. Nicht anfassen.
Neu erzeugt am 2026-08-20 (GERUEST_URL war im Auftrag nicht eingetragen).

WICHTIG (Fallstrick vom 10.08.): Zahlformatierung (Punkt -> Komma) NIEMALS auf
die ganze SVG-Zeichenkette anwenden, sonst zerbrechen die Koordinaten.
Immer nur auf den Labeltext.
"""

import functools
import json
import os
import re
import html as _html

HIER = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Quellen / Tier
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def lade_referenz():
    """referenz.json ist read-only und aendert sich innerhalb eines Laufs nie
    -- gecacht, weil sie sonst bis zu 8-9 mal pro Lauf neu gelesen wird
    (run_all.py, mmlib.build() und validate.pruefe() je Korrekturrunde).
    Neu am 28.08.2026 (V5)."""
    with open(os.path.join(HIER, "referenz.json"), encoding="utf-8") as f:
        return json.load(f)


def norm_host(host):
    """Hostnamen normalisieren. NICHT lstrip('www.') verwenden."""
    h = (host or "").strip().lower()
    h = re.sub(r"^https?://", "", h)
    h = h.split("/")[0]
    h = re.sub(r"^www\.", "", h)
    return h


def host_aus_url(url):
    return norm_host(url)


def tier_von_host(host, ref):
    h = norm_host(host)
    t = ref.get("tier", {})
    if h in [norm_host(x) for x in t.get("A", [])]:
        return "A"
    if h in [norm_host(x) for x in t.get("B", [])]:
        return "B"
    if h in [norm_host(x) for x in t.get("D", [])]:
        return "D"
    return "C"


class Belegapparat(object):
    """Verwaltet Quellen, vergibt laufende Nummern, zaehlt Belege und Links."""

    def __init__(self, data, ref):
        self.ref = ref
        self.sources = data.get("sources", {})
        self.werte = data.get("werte", {})
        self.nummer = {}
        self.reihenfolge = []
        self.link_hosts = []          # jeder gerenderte Link, für die Tier-Quote
        self.zahl_doppelt = 0
        self.zahl_einfach = 0
        self.zahl_ungueltig = 0
        self.gerendert = set()

    # -- Quellen -----------------------------------------------------------
    def src(self, key):
        s = self.sources.get(key)
        if s is None:
            return {"url": "#", "titel": "FEHLENDE QUELLE " + str(key),
                    "host": "unbekannt", "tier": "C"}
        s = dict(s)
        s.setdefault("host", host_aus_url(s.get("url", "")))
        s["tier"] = tier_von_host(s["host"], self.ref)
        return s

    def nr(self, key):
        if key not in self.nummer:
            self.nummer[key] = len(self.reihenfolge) + 1
            self.reihenfolge.append(key)
        return self.nummer[key]

    def link(self, key, text=None, klasse="qlink"):
        s = self.src(key)
        self.link_hosts.append(norm_host(s["host"]))
        titel = "%s -- %s (Tier %s)" % (s["titel"], s["host"], s["tier"])
        return ('<a class="%s" href="%s" target="_blank" rel="noopener" title="%s">%s</a>'
                % (klasse, _html.escape(s["url"], True), _html.escape(titel, True),
                   _html.escape(text if text is not None else str(self.nr(key)))))

    # -- Belegzeichen ------------------------------------------------------
    def beleg(self, a, b):
        """Hochgestellte Quelllinks. b=None -> Warndreieck."""
        teile = [self.link(a, str(self.nr(a)), "qref")]
        if b:
            teile.append(self.link(b, str(self.nr(b)), "qref"))
        else:
            teile.append('<span class="warndreieck" '
                         'title="nur eine Quelle gefunden; zweiter unabhaengiger '
                         'Beleg fehlt">&#9888;</span>')
        return '<sup class="q">' + "".join(teile) + "</sup>"

    def wert(self, key, anzeige=None, feld="wert"):
        w = self.werte.get(key)
        if w is None:
            return '<span class="fehlt">[%s?]</span>' % _html.escape(str(key))
        a, b = w.get("a"), w.get("b")
        if key not in self.gerendert:
            self.gerendert.add(key)
            if a and b:
                ha, hb = norm_host(self.src(a)["host"]), norm_host(self.src(b)["host"])
                ta, tb = self.src(a)["tier"], self.src(b)["tier"]
                if ha == hb or not (ta in ("A", "B") or tb in ("A", "B")):
                    self.zahl_ungueltig += 1
                else:
                    self.zahl_doppelt += 1
            elif a:
                self.zahl_einfach += 1
            else:
                self.zahl_ungueltig += 1
        if feld == "chg":
            roh = w.get("chg", "")
            kl = "chg-n"
            if roh.strip().startswith("+"):
                kl = "chg-p"
            elif roh.strip().startswith("-") or roh.strip().startswith("−"):
                kl = "chg-m"
            txt = _html.escape(roh)
            return '<span class="%s num">%s</span>%s' % (kl, txt, self.beleg(a, b))
        txt = anzeige if anzeige is not None else w.get("wert", "")
        return '<span class="num">%s</span>%s' % (_html.escape(str(txt)), self.beleg(a, b))

    # -- Kennzahlen --------------------------------------------------------
    def tier_quote(self):
        if not self.link_hosts:
            return 0.0
        gut = sum(1 for h in self.link_hosts
                  if tier_von_host(h, self.ref) in ("A", "B"))
        return 100.0 * gut / len(self.link_hosts)

    def quellenverzeichnis(self):
        zeilen = []
        for key in self.reihenfolge:
            s = self.src(key)
            zeilen.append(
                '<li id="q%d"><span class="qnum">%d</span> '
                '<a href="%s" target="_blank" rel="noopener">%s</a> '
                '<span class="qhost">%s &middot; Tier %s</span></li>'
                % (self.nummer[key], self.nummer[key],
                   _html.escape(s["url"], True), _html.escape(s["titel"]),
                   _html.escape(s["host"]), s["tier"]))
            self.link_hosts.append(norm_host(s["host"]))
        return '<ol class="quellen">' + "\n".join(zeilen) + "</ol>"


# --------------------------------------------------------------------------
# Platzhalteraufloesung
# --------------------------------------------------------------------------

PH = re.compile(r"\{\{([^{}]+)\}\}")


def aufloesen(text, bel):
    if text is None:
        return ""

    def ers(m):
        inhalt = m.group(1)
        if inhalt.startswith("a:"):
            _, src, txt = inhalt.split(":", 2)
            return bel.link(src, txt, "inlink")
        if inhalt.startswith("1:"):
            _, src, txt = inhalt.split(":", 2)
            out = _html.escape(txt) + bel.beleg(src, None)
            bel.zahl_einfach += 1
            return out
        if inhalt.startswith("2:"):
            _, sa, sb, txt = inhalt.split(":", 3)
            out = _html.escape(txt) + bel.beleg(sa, sb)
            ha, hb = norm_host(bel.src(sa)["host"]), norm_host(bel.src(sb)["host"])
            ta, tb = bel.src(sa)["tier"], bel.src(sb)["tier"]
            if ha == hb or not (ta in ("A", "B") or tb in ("A", "B")):
                bel.zahl_ungueltig += 1
            else:
                bel.zahl_doppelt += 1
            return out
        if inhalt.endswith("#chg"):
            return bel.wert(inhalt[:-4], feld="chg")
        if "|" in inhalt:
            key, disp = inhalt.split("|", 1)
            return bel.wert(key, disp)
        return bel.wert(inhalt)

    return PH.sub(ers, text)


# --------------------------------------------------------------------------
# Tabellen
# --------------------------------------------------------------------------

def tabelle(tab, bel):
    t = ['<div class="tabwrap"><table class="dt">']
    if tab.get("titel"):
        t.append('<caption>%s</caption>' % aufloesen(tab["titel"], bel))
    if tab.get("kopf"):
        t.append("<thead><tr>" + "".join(
            "<th>%s</th>" % aufloesen(c, bel) for c in tab["kopf"]) + "</tr></thead>")
    t.append("<tbody>")
    for z in tab.get("zeilen", []):
        t.append("<tr>" + "".join(
            "<td>%s</td>" % aufloesen(c, bel) for c in z) + "</tr>")
    t.append("</tbody></table>")
    if tab.get("fuss"):
        t.append('<p class="tabfuss">%s</p>' % aufloesen(tab["fuss"], bel))
    t.append("</div>")
    return "\n".join(t)


# --------------------------------------------------------------------------
# SVG-Chart: 1-Sigma-Kegel (blauer Balken) gegen Kurszieldistanz (oranger Punkt)
# --------------------------------------------------------------------------

def _de(x, nd=1):
    """Deutsche Zahlformatierung -- NUR auf Labeltext anwenden, nie auf die SVG."""
    s = ("%%.%df" % nd) % x
    return s.replace(".", ",")


def chart_svg(vorschau):
    # Geaendert am 21.08.2026 (C3): Ein Name braucht nur noch einen Implied Move,
    # kein Konsenskursziel mehr. Bis dahin filterte die Bedingung jeden Namen ohne
    # Kursziel heraus -- am 21.08. blieben deshalb zwei von zehn Zeilen uebrig.
    # Ohne Kursziel wird nur der Balken gezeichnet, ohne Punkt und ohne Sigma-Label.
    rows = [r for r in vorschau if r.get("implied") is not None]
    if not rows:
        return '<p class="hinweis">Keine Vorschaudaten mit Implied Move verfügbar.</p>'

    ml, mr, mt, mb = 168, 74, 44, 40
    rh = 34
    W = 900
    H = mt + rh * len(rows) + mb
    plot = W - ml - mr

    ups = [r["upside"] for r in rows if r.get("upside") is not None]
    imp_max = max(abs(r["implied"]) for r in rows)
    hi = max(imp_max, max((abs(u) for u in ups), default=0.0)) * 1.10
    lo = min(-imp_max * 1.15, min(ups, default=0.0) * 1.15, -2.0)
    if hi - lo < 1e-6:
        hi, lo = 1.0, -1.0

    def X(v):
        return ml + (v - lo) / (hi - lo) * plot

    s = []
    s.append('<svg class="mmchart" viewBox="0 0 %d %d" width="100%%" '
             'role="img" aria-label="Eingepreister Ein-Sigma-Move gegen '
             'Analystenkursziel" xmlns="http://www.w3.org/2000/svg">' % (W, H))

    # Achse
    ticks = []
    schritt = 10.0 if (hi - lo) > 45 else 5.0
    t = -60.0
    while t <= 80.0:
        if lo <= t <= hi:
            ticks.append(t)
        t += schritt
    for tv in ticks:
        x = X(tv)
        s.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" class="grid"/>'
                 % (x, mt - 12, x, H - mb + 6))
        s.append('<text x="%.2f" y="%d" class="axlab" text-anchor="middle">%s</text>'
                 % (x, H - mb + 22, _de(tv, 0) + " %"))
    x0 = X(0.0)
    s.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" class="zero"/>'
             % (x0, mt - 16, x0, H - mb + 6))
    s.append('<text x="%.2f" y="%d" class="axtitle" text-anchor="middle">'
             'Spot</text>' % (x0, mt - 22))

    for i, r in enumerate(rows):
        y = mt + i * rh + rh / 2.0
        xa, xb = X(-abs(r["implied"])), X(abs(r["implied"]))
        # Name
        s.append('<text x="%d" y="%.2f" class="rowlab" text-anchor="end" '
                 'dominant-baseline="middle">%s</text>'
                 % (ml - 14, y, _html.escape(r["name"])))
        # 1-Sigma-Balken
        s.append('<rect x="%.2f" y="%.2f" width="%.2f" height="12" rx="4" '
                 'class="bar1s"><title>%s: eingepreister Move plus/minus %s %%'
                 '</title></rect>'
                 % (xa, y - 6.0, max(xb - xa, 2.0),
                    _html.escape(r["name"]), _de(abs(r["implied"]), 1)))
        # Kursziel-Punkt -- entfaellt, wenn kein Konsenskursziel belegt ist (C3)
        if r.get("upside") is None:
            continue
        xd = X(r["upside"])
        s.append('<circle cx="%.2f" cy="%.2f" r="7.5" class="dotring"/>' % (xd, y))
        s.append('<circle cx="%.2f" cy="%.2f" r="5.5" class="dot"><title>%s: '
                 'Konsenskursziel %s %% vom Spot</title></circle>'
                 % (xd, y, _html.escape(r["name"]), _de(r["upside"], 1)))
        # Sigma-Label -- Kollisionsregel: rechts, sonst links
        if r.get("sigma") is None:
            continue
        lab = _de(r["sigma"], 2) + " σ"
        breite = 8.0 * len(lab)
        if xd + 12 + breite < W - mr + 66:
            lx, anker = xd + 12, "start"
        else:
            lx, anker = xd - 12, "end"
        # Kollisionsregel: das Label darf nie auf dem 1-Sigma-Balken liegen.
        # Liegt der Punkt innerhalb des Kegels, wandert das Label hinter das
        # Balkenende statt neben den Punkt.
        if anker == "start" and lx < xb + 12:
            lx = xb + 12
        if anker == "end" and lx - breite < xb + 12:
            lx, anker = max(xd + 12, xb + 12), "start"
        s.append('<text x="%.2f" y="%.2f" class="siglab" text-anchor="%s" '
                 'dominant-baseline="middle">%s</text>' % (lx, y, anker, lab))

    s.append("</svg>")
    svg = "\n".join(s)   # bewusst KEIN globales replace(".", ",")

    legende = (
        '<p class="chartlegende"><span class="lg lg-bar"></span> blauer Balken = '
        'von Optionen eingepreister Move (&plusmn;1&nbsp;&sigma;) &nbsp;&middot;&nbsp; '
        '<span class="lg lg-dot"></span> oranger Punkt = 12M-Konsenskursziel, '
        'Abstand vom Spot &nbsp;&middot;&nbsp; Beschriftung = Distanz in &sigma;. '
        'Liegt der Punkt weit außerhalb des Balkens, ist die Vola gegenüber der '
        'Analystenerwartung billig.</p>')
    return '<figure class="chartfig">' + svg + legende + "</figure>"


# --------------------------------------------------------------------------
# Bloecke
# --------------------------------------------------------------------------

def block(b, bel, data):
    typ = b.get("typ", "p")
    if typ == "p":
        return "<p>%s</p>" % aufloesen(b.get("text", ""), bel)
    if typ == "lead":
        return '<p class="lead">%s</p>' % aufloesen(b.get("text", ""), bel)
    if typ == "h3":
        return "<h3>%s</h3>" % aufloesen(b.get("text", ""), bel)
    if typ == "ol":
        return "<ol class=\"nummeriert\">" + "".join(
            "<li>%s</li>" % aufloesen(i, bel) for i in b.get("items", [])) + "</ol>"
    if typ == "ul":
        return "<ul>" + "".join(
            "<li>%s</li>" % aufloesen(i, bel) for i in b.get("items", [])) + "</ul>"
    if typ == "tabelle":
        tab = data.get("tabellen", {}).get(b.get("ref"), {})
        return tabelle(tab, bel)
    if typ == "chart":
        return chart_svg(data.get("vorschau", []))
    if typ == "hinweis":
        return '<p class="hinweis">%s</p>' % aufloesen(b.get("text", ""), bel)
    return "<p>%s</p>" % aufloesen(b.get("text", ""), bel)


def sektion(sek, bel, data):
    out = ['<section class="sek" id="s%s">' % sek.get("nr")]
    out.append('<h2><span class="seknr">%s</span>%s</h2>'
               % (sek.get("nr"), _html.escape(sek.get("titel", ""))))
    for b in sek.get("bloecke", []):
        out.append(block(b, bel, data))
    out.append("</section>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Pruefbericht
# --------------------------------------------------------------------------

def pruefbericht_html(rep, bel, nr=10):
    """Pruefbericht als letzte Sektion der PDF-Vollausgabe.

    Geaendert am 21.08.2026 (C2): Der Bericht erscheint nur noch in der
    Vollausgabe, nicht mehr im Mail-Body -- `build_mail.py` schneidet ihn heraus.
    Die Nummer richtet sich nach der Zahl der Inhaltssektionen, damit eine neue
    Sektion 10 den Bericht auf 11 schiebt statt ihn zu ueberschreiben.
    """
    if not rep:
        return ""
    n = len(rep.get("befunde", []))
    kopf = ('Die automatische Formatkontrolle meldet <b>%d Befund%s</b>. '
            'Die Ausgabe wurde trotzdem versendet -- die Kontrolle hält den '
            'Versand nicht auf.' % (n, "" if n == 1 else "e"))
    t = ['<section class="sek pruef" id="s%d">' % nr,
         '<h2><span class="seknr">%d</span>Pruefbericht</h2>' % nr,
         "<p>%s</p>" % kopf]
    k = rep.get("kennzahlen", [])
    t.append('<div class="tabwrap"><table class="dt"><thead><tr>'
             "<th>Kennzahl</th><th>Wert</th><th>Soll</th><th>Status</th>"
             "</tr></thead><tbody>")
    for row in k:
        t.append("<tr><td>%s</td><td class=\"num\">%s</td><td>%s</td>"
                 '<td class="%s">%s</td></tr>'
                 % (_html.escape(row[0]), _html.escape(str(row[1])),
                    _html.escape(str(row[2])),
                    "ok" if row[3] else "nok", "erfuellt" if row[3] else "Befund"))
    t.append("</tbody></table></div>")
    if n:
        t.append("<h3>Befunde</h3><ol class=\"befunde\">")
        for b in rep["befunde"]:
            t.append("<li>%s</li>" % aufloesen(b, bel))
        t.append("</ol>")
    else:
        t.append("<p>Kein Befund.</p>")
    for z in rep.get("anmerkungen", []):
        t.append('<p class="hinweis">%s</p>' % aufloesen(z, bel))
    t.append('<p class="hinweis">Die Kontrolle prueft Vollstaendigkeit und '
             "Form, nicht die inhaltliche Richtigkeit der Zahlen. Jede Zahl ist "
             "vor der Verwendung im Kundengespräch gegen Bloomberg oder "
             "Refinitiv zu prüfen.</p>")
    t.append("</section>")
    return "\n".join(t)


# --------------------------------------------------------------------------
# Dokumentbau
# --------------------------------------------------------------------------

def build(data, rep=None):
    ref = lade_referenz()
    bel = Belegapparat(data, ref)
    meta = data.get("meta", {})

    inhalt = []
    nummern = []
    for sek in data.get("sektionen", []):
        inhalt.append(sektion(sek, bel, data))
        try:
            nummern.append(int(sek.get("nr")))
        except (TypeError, ValueError):
            pass
    if rep is not None:
        # Pruefbericht bekommt die naechste freie Nummer (C4: neue Sektion 10)
        inhalt.append(pruefbericht_html(rep, bel, max(nummern or [9]) + 1))

    n = len(rep.get("befunde", [])) if rep else 0
    if rep is None:
        pruefzeile = ("Automatische Formatkontrolle: l\u00e4uft \u2013 Ergebnis im "
                      "Pruefbericht am Ende.")
    elif n == 0:
        pruefzeile = ("Automatische Formatkontrolle: ohne Befund \u2013 siehe "
                      "Pruefbericht am Ende.")
    else:
        pruefzeile = ("Automatische Formatkontrolle: %d Befund%s \u2013 siehe "
                      "Pruefbericht am Ende." % (n, "" if n == 1 else "e"))

    legende = ('Belege: hochgestellte Ziffern sind Quelllinks und verweisen auf '
               'das Quellenverzeichnis. <span class="warndreieck">&#9888;</span> '
               "= nur einfach belegt.")

    quellen = bel.quellenverzeichnis()

    with open(os.path.join(HIER, "template.html"), encoding="utf-8") as f:
        tpl = f.read()

    doc = (tpl
           .replace("__WOCHENTAG__", _html.escape(meta.get("wochentag", "")))
           .replace("__DATUM_LANG__", _html.escape(meta.get("datum_lang", "")))
           .replace("__DATUM__", _html.escape(meta.get("datum", "")))
           .replace("__DATENSTAND__", _html.escape(meta.get("datenstand", "")))
           .replace("__PRUEFZEILE__", pruefzeile)
           .replace("__LEGENDE__", legende)
           .replace("__INHALT__", "\n".join(inhalt))
           .replace("__QUELLEN__", quellen))

    kenn = {
        "doppelt": bel.zahl_doppelt,
        "einfach": bel.zahl_einfach,
        "ungueltig": bel.zahl_ungueltig,
        "tier_quote": bel.tier_quote(),
        "links": len(bel.link_hosts),
        "quellen": len(bel.reihenfolge),
    }
    return doc, kenn


def text_aus_html(h):
    h = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = _html.unescape(h)
    return re.sub(r"\s+", " ", h).strip()


def woerter(h):
    return len([w for w in text_aus_html(h).split(" ") if w.strip()])
