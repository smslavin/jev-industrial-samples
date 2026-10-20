"""Spoof a brownfield PLC namespace from the clean AvevaWaterOPC model, with an answer key.

    python dirtier.py medium 7          # writes dirty/medium-7/{galaxy,opcua_browse,expected}.json

The galaxy side stays clean: it is the AvevaWaterOPC object model from opcua-mcp's
simulator.py. The OPC-UA side is rebuilt the way a PLC programmer might have built it:
different naming conventions per PLC, blank descriptions, other units, look-alike
decoys, missing signals. Because the mess is generated, the true mapping is known.

The naming rules are this author's idea of a messy plant, not field data; treat the
results as a stress test of the mapper, not a measurement of real-world accuracy.
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent

# Clean model, copied from mcp-servers/opcua-mcp/simulator.py INSTANCES (value ranges only).
# Units are assumed; the simulator does not define them.
CLEAN = [
    ("Pump", "RawWater_01", "Raw water pump 1", {"Flow": (0, 500), "Pressure": (0, 10), "Running": True, "Power": (0, 75)}),
    ("Pump", "RawWater_02", "Raw water pump 2", {"Flow": (0, 500), "Pressure": (0, 10), "Running": True, "Power": (0, 75)}),
    ("Pump", "HighService_01", "High service pump 1", {"Flow": (0, 500), "Pressure": (2, 10), "Running": True, "Power": (0, 75)}),
    ("Pump", "HighService_02", "High service pump 2", {"Flow": (0, 500), "Pressure": (2, 10), "Running": False, "Power": (0, 75)}),
    ("Tank", "Clarifier_01", "Clarifier", {"Level": (0, 100), "pH": (6.5, 8.5), "Turbidity": (0, 5)}),
    ("Tank", "FinishedWater_01", "Finished water tank", {"Level": (0, 100), "pH": (6.8, 7.8), "Turbidity": (0, 1)}),
    ("Dosing", "Chlorine_01", "Chlorine dosing", {"FlowRate": (0, 10), "Running": True, "TankLevel": (20, 100)}),
    ("Dosing", "Fluoride_01", "Fluoride dosing", {"FlowRate": (0, 10), "Running": True, "TankLevel": (20, 100)}),
    ("UV", "UV_01", "UV reactor 1", {"Intensity": (85, 100), "Running": True, "LampHours": (0, 10000)}),
    ("UV", "UV_02", "UV reactor 2", {"Intensity": (85, 100), "Running": False, "LampHours": (0, 10000)}),
]

UDA = {  # galaxy attribute: (units, description)
    "Flow": ("m3/h", "Pump flow"), "Pressure": ("bar", "Discharge pressure"), "Running": (None, "Running status"),
    "Power": ("kW", "Motor power"), "Level": ("%", "Tank level"), "pH": ("pH", "pH"), "Turbidity": ("NTU", "Turbidity"),
    "FlowRate": ("L/h", "Chemical dosing rate"), "TankLevel": ("%", "Chemical day tank level"),
    "Intensity": ("%", "UV intensity"), "LampHours": ("h", "Lamp run hours"),
}

# Per-signal names in three conventions:
#   A = abbreviated tags in an equipment folder, B = ISA loop tags, C = Siemens-style German data block.
# Each entry: (A, B prefix, B suffix, C, English description, German description)
SIG = {
    "Flow":      ("FT_PV",    "FT",  "_PV",  "Q_IST",       "Flow",              "Durchfluss Istwert"),
    "Pressure":  ("PT_PV",    "PT",  "_PV",  "P_IST",       "Discharge pressure", "Druck Istwert"),
    "Running":   ("RUN_FB",   "YS",  "",     "BM_LAEUFT",   "Run feedback",      "Betriebsmeldung laeuft"),
    "Power":     ("KW",       "JI",  "_PV",  "P_EL",        "Motor power",       "Elektrische Leistung"),
    "Level":     ("LT_PV",    "LT",  "_PV",  "FUELLSTAND",  "Level",             "Fuellstand"),
    "pH":        ("PH_PV",    "AIT", "A_PV", "PH_WERT",     "pH",                "pH-Wert"),
    "Turbidity": ("NTU_PV",   "AIT", "B_PV", "TRUEBUNG",    "Turbidity",         "Truebung"),
    "FlowRate":  ("FLOW",     "FT",  "_PV",  "DOSIERMENGE", "Dosing flow",       "Dosiermenge"),
    "TankLevel": ("TK_LVL",   "LT",  "T_PV", "TANK_FS",     "Day tank level",    "Tank Fuellstand"),
    "Intensity": ("UVI",      "AIT", "_PV",  "UV_INTENS",   "UV intensity",      "UV-Intensitaet"),
    "LampHours": ("LAMP_HRS", "KQI", "_PV",  "LAMPE_BH",    "Lamp hours",        "Lampe Betriebsstunden"),
}

# Look-alikes a careless mapping would grab: (A, B as format with {n}, C, data_type, eu, English, German)
DECOYS = {
    "Flow":      [("FT_SP", "FIC{n}_SP", "Q_SOLL", "Float", "m3/h", "Flow setpoint", "Durchfluss Sollwert")],
    "Pressure":  [("PT_HI_SP", "PAH{n}_SP", "P_GW_MAX", "Float", "bar", "High pressure limit", "Druck Grenzwert max")],
    "Running":   [("RUN_CMD", "HS{n}_CMD", "BE_EIN", "Boolean", None, "Run command", "Befehl ein"),
                  ("AUTO_SEL", "HS{n}_AUTO", "BA_AUTO", "Boolean", None, "Auto selected", "Betriebsart Automatik")],
    "Power":     [("AMPS", "II{n}_PV", "STROM", "Float", "A", "Motor current", "Motorstrom")],
    "Level":     [("LT_H", "LAH{n}", "FS_MAX", "Boolean", None, "High level", "Fuellstand max"),
                  ("LT_L", "LAL{n}", "FS_MIN", "Boolean", None, "Low level", "Fuellstand min")],
    "pH":        [("PH_TEMP", "TT{n}_PV", "PH_TEMP", "Float", "degC", "pH probe temperature", "Temperatur pH-Sonde")],
    "Turbidity": [("NTU_RAW", "AIT{n}B_RAW", "TRUEB_ROH", "Int16", None, "Turbidity raw counts", "Truebung Rohwert")],
    "FlowRate":  [("SPM", "SY{n}_PV", "HUBFREQ", "Float", "1/min", "Stroke rate", "Hubfrequenz")],
    "TankLevel": [("TK_LSL", "LSL{n}T", "TANK_LEER", "Boolean", None, "Tank low level switch", "Tank leer")],
    "Intensity": [("UVI_LO_SP", "AIL{n}_SP", "UV_GW_MIN", "Float", "%", "Low intensity limit", "UV Grenzwert min")],
    "LampHours": [("LAMP_STARTS", "KQI{n}_STARTS", "LAMPE_STARTS", "Int32", None, "Lamp starts", "Lampe Starts")],
}

# Units a PLC programmer might have used instead: galaxy unit -> (PLC unit, factor)
OTHER_UNITS = {"bar": ("psi", 14.5038), "m3/h": ("gpm", 4.40287), "%": ("", 0.01), "kW": ("hp", 1.34102)}

FOLDER_A = {"RawWater": "RW_PMP", "HighService": "HS_PMP", "Clarifier": "CLAR", "FinishedWater": "FW_TK",
            "Chlorine": "CL2_DOSE", "Fluoride": "FL_DOSE", "UV": "UV"}
LOOP = {"RawWater_01": 101, "RawWater_02": 102, "Clarifier_01": 201, "HighService_01": 301, "HighService_02": 302,
        "FinishedWater_01": 401, "Chlorine_01": 501, "Fluoride_01": 502, "UV_01": 601, "UV_02": 602}
PLC_OF = {"Pump": "PLC1", "Tank": "PLC2", "Dosing": "PLC2", "UV": "PLC3"}

LEVELS = {
    #          conventions per PLC                         blank  units  decoys drops  spares offset
    "easy":   ({"PLC1": "A", "PLC2": "A", "PLC3": "A"},   0.2,   0.0,   False, 0.0,   False, False),
    "medium": ({"PLC1": "A", "PLC2": "B", "PLC3": "A"},   0.5,   0.3,   True,  0.1,   True,  False),
    "hard":   ({"PLC1": "A", "PLC2": "B", "PLC3": "C"},   0.8,   0.5,   True,  0.15,  True,  False),
    # Medium mess plus raw water pumps 1 and 2 wired to each other's PLC folders. No name-based
    # method can catch this; it isolates the case that needs a field check.
    "swapped": ({"PLC1": "A", "PLC2": "B", "PLC3": "A"},  0.5,   0.3,   True,  0.1,   True,  True),
}


def generate(level: str, seed: int) -> tuple[dict, dict, dict]:
    conventions, p_blank, p_units, decoys, p_drop, spares, offset = LEVELS[level]
    rng = random.Random(seed)

    def value(spec):
        if isinstance(spec, bool):
            return spec
        lo, hi = spec
        return round(rng.uniform(lo + 0.2 * (hi - lo), hi - 0.2 * (hi - lo)), 2)

    def desc(en, de, conv):
        return "" if rng.random() < p_blank else (de if conv == "C" else en)

    galaxy, browse, expected = {}, {}, {}
    db = 10
    for obj_type, inst, inst_desc, attrs in CLEAN:
        galaxy[inst] = {"template": f"${obj_type}", "area": obj_type, "description": inst_desc, "udas": {
            a: {"type": "Boolean" if isinstance(spec, bool) else "Float", "description": UDA[a][1],
                **({"units": UDA[a][0]} if UDA[a][0] else {})}
            for a, spec in attrs.items()}}

        plc = PLC_OF[obj_type]
        conv = conventions[plc]
        base, num = inst.rsplit("_", 1)
        number = int(num)
        if offset and base == "RawWater":
            number = 3 - number  # the classic trap: PLC numbering doesn't follow the P&ID
        loop = LOOP[f"{base}_{number:02d}"]
        if conv == "A":
            folder = f"{plc}.{FOLDER_A[base]}_{number}"
        elif conv == "B":
            folder = f"{plc}.U{loop}"
        else:
            folder, db = f"{plc}.DB{db}", db + 1
        nodes = browse.setdefault(folder, {})

        for a, spec in attrs.items():
            a_name, b_pre, b_suf, c_name, en, de = SIG[a]
            tag = {"A": a_name, "B": f"{b_pre}{loop}{b_suf}", "C": c_name}[conv]
            if a == "Running" and conv == "B":
                tag = f"YS{loop}"
            if rng.random() < p_drop:
                expected[f"{inst}.{a}"] = None
            else:
                node = {"data_type": "Boolean" if isinstance(spec, bool) else "Float", "description": desc(en, de, conv),
                        "value": value(spec)}
                units = UDA[a][0]
                if units:
                    if units in OTHER_UNITS and rng.random() < p_units:
                        units, factor = OTHER_UNITS[units]
                        node["value"] = round(node["value"] * factor, 3)
                    node["eu"] = units
                nodes[tag] = node
                expected[f"{inst}.{a}"] = f"{folder}.{tag}"

            if decoys:
                for d_a, d_b, d_c, d_type, d_eu, d_en, d_de in DECOYS[a]:
                    d_tag = {"A": d_a, "B": d_b.format(n=loop), "C": d_c}[conv]
                    d_val = rng.random() < 0.3 if d_type == "Boolean" else (rng.randint(0, 4000) if d_type.startswith("Int") else value((0, 100)))
                    nodes[d_tag] = {"data_type": d_type, "description": desc(d_en, d_de, conv), "value": d_val,
                                    **({"eu": d_eu} if d_eu else {})}
        if spares and rng.random() < 0.4:
            nodes[f"SPARE_{rng.randint(1, 20):02d}"] = {"data_type": "Float", "description": "", "value": 0.0}

    for plc in sorted(set(PLC_OF.values())):
        browse[f"{plc}.SYS"] = {
            "HEARTBEAT": {"data_type": "Int16", "description": "PLC heartbeat", "value": rng.randint(0, 32767)},
            "CPU_LOAD": {"data_type": "Float", "description": "", "eu": "%", "value": value((5, 60))},
            "COMM_OK": {"data_type": "Boolean", "description": "Comms healthy", "value": True},
        }
    # Folder order should carry no information.
    browse = dict(rng.sample(sorted(browse.items()), len(browse)))
    return galaxy, browse, expected


def write(level: str, seed: int) -> Path:
    out = HERE / "dirty" / f"{level}-{seed}"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in zip(("galaxy", "opcua_browse", "expected"), generate(level, seed)):
        (out / f"{name}.json").write_text(json.dumps(data, indent=2))
    return out


if __name__ == "__main__":
    print(write(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1))
