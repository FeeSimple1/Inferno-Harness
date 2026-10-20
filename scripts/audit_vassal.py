"""Read-only component/setup cross-check against a locally supplied Vassal module.

Usage: PYTHONPATH=src python scripts/audit_vassal.py /path/Inferno_1.0.vmod
No module artwork or saved games are copied into the repository. Printed
artwork and official errata remain authoritative over module automation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from inferno import static_data as sd
from inferno.scenarios import load_scenario

MODULE_SHA256 = "cbe05ecd23f63859d675a6fe27b027fc2c3ac3dfacf4e1987da6a067c2535464"
LORDS = {
    "Ghibellines1": "siena", "Ghibellines2": "pisa", "Ghibellines3": "giordano",
    "Ghibellines4": "santa_fiora", "Ghibellines5": "astimberg", "Ghibellines6": "provenzano",
    "Ghibellines7": "siena_comune", "Guelphs1": "firenze", "Guelphs2": "lucca",
    "Guelphs3": "arezzo", "Guelphs4": "orvieto", "Guelphs5": "colle",
    "Guelphs6": "guido_guerra", "Guelphs7": "firenze_comune",
}
ALIASES = {"West Lombardia": "Lombardia-Bologna West", "East Lombardia": "Lombardia-Bologna East"}


def normalized(text):
    # This extractor reads names/numbers only, never executes module traits.
    return re.sub(r"\\+", "", text)


def properties(text):
    head, tail = normalized(text).rsplit("\tpiece;", 1)
    values = tail.split("/", 1)[1].split("\t")
    traits = head.split("/", 2)[2].split("\t")
    return {t.split(";")[1]: v for t, v in zip(reversed(traits), reversed(values[:-1]))
            if t.startswith("mark;")}


def placed(text):
    return Counter(re.findall(r"prototype;([^\t]+)\tpiece;", normalized(text)))


def forces(components):
    return {("Armigieri" if k == "Armigeri" else k): v for k, v in components.items()
            if k in sd.UNITS or k == "Armigeri"}


def audit(path):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != MODULE_SHA256:
        raise ValueError("Unknown module version/hash; review its format and exceptions before comparing.")
    z = zipfile.ZipFile(io.BytesIO(raw))
    root = ET.fromstring(z.read("buildFile.xml"))
    protos = {e.attrib["name"]: e.text for e in root.iter() if e.tag.endswith(".PrototypeDefinition")}
    checks, differences, exceptions = [], [], []

    def check(label, actual, expected):
        checks.append(label)
        if actual != expected:
            if (label in ("D/provenzano/location", "D/santa_fiora/location")
                    and actual == "Montepulciano" and expected == "Montalcino"):
                exceptions.append({"check": label, "harness": actual, "module": expected,
                                   "authority": "Rules of Play Scenario D, p28"})
                return
            differences.append({"check": label, "harness": actual, "module": expected})

    for mid, lid in LORDS.items():
        data = sd.LORDS[sd.LORD_NAMES[lid]]
        components = placed(protos["Mat " + mid])
        expected = forces(components)
        # Module automatically supplies Carroccio with a Comune mat. The
        # harness supplies it in the explicit 3.5.3 selection instead.
        if not data.get("comune_of"):
            check(lid + "/forces", data["forces"], expected)
            props = properties(protos["Stats " + mid])
            for key, field in [("C", "Command"), ("L", "Lordship"), ("S", "Service")]:
                printed = int(props[field])
                if lid == "orvieto" and key == "C":
                    printed = 3  # GuelphMats-3_b_t.png and PAC-Guelphs.jpg
                check(lid + "/" + key, data["ratings"][key], printed)
        assets = {}
        for name, count in components.items():
            match = re.fullmatch(r"(Coin|Cart|Ship|Provender) Marker (\d+)", name)
            if match:
                assets[match[1]] = int(match[2]) * count
        check(lid + "/assets", data["assets"], assets)
        expected_vassals = []
        for name, text in protos.items():
            if name.startswith("Service " + mid + "."):
                props = properties(text)
                expected_vassals.append((int(props["Service"]), sorted(forces(placed(text)).items())))
        actual_vassals = [(v.get("service_rating", 0), sorted(v["forces"].items())) for v in data["vassals"]]
        check(lid + "/vassal-force-service-multiset", sorted(actual_vassals), sorted(expected_vassals))
    check("Altopascio/service", sd.ALTOPASCIO_VASSAL["service_rating"],
          int(properties(protos["Service Altopascio"])["Service"]))
    check("Altopascio/forces", sd.ALTOPASCIO_VASSAL["forces"], forces(placed(protos["Service Altopascio"])))

    # Printed allegiance/type on the module's Location prototypes.
    for name, text in protos.items():
        canonical = ALIASES.get(name, name)
        if canonical not in sd.LOCALES:
            continue
        match = re.search(r"prototype;Location (?:(Guelph|Ghibelline) )?(City|Town|Castle|Outpost)", normalized(text))
        if match:
            check(canonical + "/type", sd.LOCALES[canonical]["type"], match[2].lower())
            if match[1]:
                check(canonical + "/allegiance", sd.LOCALES[canonical]["allegiance"], match[1].lower())

    # Decode only public predefined starting setups. Region nearest-neighbor
    # applies to snapped Lord markers, not arbitrary ongoing-game coordinates.
    regions = [(ALIASES.get(e.attrib["name"], e.attrib["name"]), int(e.attrib["originx"]), int(e.attrib["originy"]))
               for e in root.iter() if e.tag.endswith(".Region")
               and ALIASES.get(e.attrib["name"], e.attrib["name"]) in sd.LOCALES]
    zones = []
    for e in root.iter():
        if e.tag.endswith(".Zone") and re.fullmatch(r"Turn \d+", e.attrib.get("name", "")):
            pts = [tuple(map(int, x.split(","))) for x in e.attrib["path"].split(";")]
            zones.append((int(e.attrib["name"][5:]), min(x for x,y in pts), min(y for x,y in pts),
                          max(x for x,y in pts), max(y for x,y in pts)))
    for fname in sorted(n for n in z.namelist() if re.match(r"Scen[1-6]-", n)):
        scenario = chr(64 + int(fname[4]))
        state = load_scenario(scenario, 1)
        save = zipfile.ZipFile(io.BytesIO(z.read(fname))).read("savedGame").decode()
        assert save.startswith("!VCSK")
        encoded = bytes.fromhex(save[5:])
        commands = bytes(b ^ encoded[0] for b in encoded[1:]).decode().split("\x1b")
        for command in commands:
            if not command.startswith("+/") or "\tpiece;" not in command:
                continue
            text = normalized(command)
            is_cylinder = "CylinderPurple" in text or "CylinderYellow" in text
            is_service = "mark;ServiceMarkerLord" in text
            if not (is_cylinder or is_service):
                continue
            # LordID precedes nested sendto traits; parse its matching state
            # using Stats names instead of shifted offsets in expanded saves.
            names = re.findall(r"basicName;([^\t]+)", text)
            lid = None
            for mid, slug in LORDS.items():
                full = re.findall(r"basicName;([^\t]+)", normalized(protos["Stats " + mid]))
                if full and full[0] in names:
                    lid = slug
                    break
            if lid is None or state["lords"][lid].get("comune_of"):
                continue  # unused Comune display cylinders are not in-play Lords
            loc = text.split("\t")[-1].split(";")
            mapname, x, y = loc[0], int(loc[1]), int(loc[2])
            lord = state["lords"][lid]
            if mapname == "Removed From Game":
                check(scenario + "/" + lid + "/removed", lord["status"], "removed")
                continue
            if mapname != "Main Map":
                continue
            turns = [n for n,a,b,c,d in zones if a<=x<=c and b<=y<=d]
            if turns:
                field = "calendar_box" if is_cylinder else "service_box"
                check(scenario + "/" + lid + "/" + field, lord[field], turns[0])
            elif is_cylinder:
                place = min(regions, key=lambda a:(a[1]-x)**2+(a[2]-y)**2)[0]
                check(scenario + "/" + lid + "/location", lord["location"], place)
    return {"module_version": root.attrib["version"], "sha256": digest,
            "checks": len(checks), "differences": differences, "known_setup_exceptions": exceptions,
            "limits": "No dynamic rules equivalence; Orvieto Command uses printed 3; Comune Carroccio accounting differs. See VASSAL_AUDIT.md."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    result = audit(parser.parse_args().module)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(bool(result["differences"]))
