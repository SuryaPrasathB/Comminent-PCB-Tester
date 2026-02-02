# config.py
# =====================================================
# PCB Tester – CENTRAL CONFIGURATION
# =====================================================

import logging
from datetime import datetime

from src.core.logger import logger

# =====================================================
# SERIAL / MODBUS COMMUNICATION SETTINGS
# =====================================================

SERIAL_SETTINGS = {
    "baudrate": 115200,  # CHANGE if required
    "parity": "N",  # 'N', 'E', 'O'
    "stopbits": 1,
    "bytesize": 8,
    "timeout": 1.0,  # seconds
    "exclusive": True  # IMPORTANT for Windows
}

logger.info("SERIAL_SETTINGS loaded")

NEUTRAL_OPTIONS = ["NC", "C"]
VOLTAGE_TAPPINGS = ["NC", "144V", "240V", "265V", "500V", "510V", "520V", "530V"]
CURRENT_TAPPINGS = ["0A", "0.5A", "1.25A", "2.5A"]

'''
    //=======================================================
    Transformer tapping:

    '138V': 1, // VLL = 240; 
    '144V': 2,
    '240V': 3,
    '265V': 4,
    '288V': 5, // VLL = 500; 
    '295V': 6, // VLL = 510; 
    '300V': 7, // VLL = 520; 
    '306V': 8, // VLL = 530; 
    //=======================================================
     PLC Coil mapping:

    'NEUTRAL': 0,

    // ================= R Phase =================
    'R_138': 1,   // VLL = 240
    'R_144': 2,
    'R_240': 3,
    'R_265': 4,
    'R_288': 5,   // VLL = 500
    'R_295': 6,   // VLL = 510
    'R_300': 7,   // VLL = 520
    'R_306': 8,   // VLL = 530

    // ================= Y Phase =================
    'Y_138': 9,   // VLL = 240
    'Y_144': 10,
    'Y_240': 11,
    'Y_265': 12,
    'Y_288': 13,  // VLL = 500
    'Y_295': 14,  // VLL = 510
    'Y_300': 15,  // VLL = 520
    'Y_306': 16,  // VLL = 530

    // ================= B Phase =================
    'B_138': 17,  // VLL = 240
    'B_144': 18,
    'B_240': 19,
    'B_265': 20,
    'B_288': 21,  // VLL = 500
    'B_295': 22,  // VLL = 510
    'B_300': 23,  // VLL = 520
    'B_306': 24   // VLL = 530

    //=========================================
    'CUR1_0_5':  25, // 1st PCB
    'CUR1_1_25': 26, // 1st PCB
    'CUR1_2_5':  27, // 1st PCB

    'CUR2_0_5':  28, // 2nd PCB
    'CUR2_1_25': 29, // 2nd PCB
    'CUR2_2_5':  30, // 2nd PCB

    //=============================================
    'IMP1_R': 31, // 1st PCB
    'IMP1_Y': 32, // 1st PCB
    'IMP1_B': 33  // 1st PCB
    'IMP1_N': 33  // 1st PCB

    'IMP2_R': 35, // 2nd PCB
    'IMP2_Y': 36, // 2nd PCB
    'IMP2_B': 37  // 2nd PCB                                                                                                                                        
    'IMP2_N': 38  // 1st PCB
    //=============================================

    Voltage Part - 25 No.s
    Current      - 3 + 3  
    Impedance    - 4 + 4

    //=======================================================
    UI representation:

'''


# =====================================================
# AUTO-GENERATED PLC COILS (NC and 0 REMOVED)
# =====================================================

def generate_plc_coils(voltage_tappings, current_tappings, start_addr=1):
    logger.info(
        f"generate_plc_coils called | "
        f"Voltage taps={voltage_tappings}, "
        f"Current taps={current_tappings}, "
        f"Start addr={start_addr}"
    )
    coils = {}
    addr = start_addr

    # ---- Neutral relay (only C needs relay) ----
    coils["NEUTRAL"] = addr
    addr += 1

    # ---- Voltage selection coils (skip NC) ----
    for phase in ("R", "Y", "B"):
        for tap in voltage_tappings:
            if tap == "NC":
                continue  # ❌ no relay for NC
            tap_key = tap.replace("V", "")
            coils[f"{phase}_{tap_key}"] = addr
            addr += 1

    # ---- Current selection coils (skip 0) ----
    for cur in current_tappings:
        if cur == "0A":
            continue  # ❌ no relay for 0
        cur_key = cur.replace("A", "").replace(".", "_")
        coils[f"CUR_{cur_key}"] = addr
        addr += 1

    # ---- Impedance test coils ----
    for phase in ("R", "Y", "B"):
        coils[f"IMP_{phase}"] = addr
        addr += 1

    logger.info(f"PLC coils generated | Total coils={len(coils)}")

    return coils


# =====================================================
# SLAVE DEVICE DEFINITIONS (SINGLE SOURCE OF TRUTH)
# =====================================================
SLAVE_DEVICES = {

    "QR_SCANNER_1": {
        "read_cmd": "015404",  # in Hex
        "display_name": "QR_Code_Scanner_1"
    },

    "QR_SCANNER_2": {
        "read_cmd": "015404",  # in Hex
        "display_name": "QR_Code_Scanner_2"
    },

    "PLC": {
        "slave_id": 1,
        "coils": generate_plc_coils(
            VOLTAGE_TAPPINGS,
            CURRENT_TAPPINGS
        ),
        "display_name": "PLC"
    },

    "AC_METER": {
        "slave_id": 2,
        "endian": "CDAB",
        "registers": {
            "R_VOLTAGE": 0x008E,
            "Y_VOLTAGE": 0x0090,
            "B_VOLTAGE": 0x0092,
        },
        "reads": {
            "r_v": "R_VOLTAGE",
            "y_v": "Y_VOLTAGE",
            "b_v": "B_VOLTAGE",
        },
        "display_name": "Ac Meter"
    },

    "IMP_METER_1": {
        "slave_id": 3,
        "endian": "ABCD",
        "registers": {
            "R_N_IMP": 0x0000,
            "Y_N_IMP": 0x0000,
            "B_N_IMP": 0x0000,
        },
        "reads": {
            "imp_rn_1": "R_N_IMP",
            "imp_yn_1": "Y_N_IMP",
            "imp_bn_1": "B_N_IMP",
        },
        "display_name": "Impedance Meter_1"
    },

    "IMP_METER_2": {
        "slave_id": 4,
        "endian": "ABCD",
        "registers": {
            "R_N_IMP": 0x0000,
            "Y_N_IMP": 0x0000,
            "B_N_IMP": 0x0000,
        },
        "reads": {
            "imp_rn_2": "R_N_IMP",
            "imp_yn_2": "Y_N_IMP",
            "imp_bn_2": "B_N_IMP",
        },
        "display_name": "Impedance Meter 2"
    },

    "DC_V_METER_1": {
        "slave_id": 17,
        "endian": "ABCD",
        "registers": {
            "DC_VOLTAGE": 0x0BB7,
        },
        "reads": {
            "dc_v": "DC_VOLTAGE",
        },
        "display_name": "Dc Voltmeter 1"
    },

    "DC_V_METER_2": {
        "slave_id": 17,
        "endian": "ABCD",
        "registers": {
            "DC_VOLTAGE": 0x0BB7,
        },
        "reads": {
            "dc_v": "DC_VOLTAGE",
        },
        "display_name": "Dc Voltmeter 2"
    },

    "DC_I_METER_1": {
        "slave_id": 18,
        "endian": "ABCD",
        "registers": {
            "DC_CURRENT": 0x0BB7,
        },
        "reads": {
            "dc_v": "DC_CURRENT",
        },
        "display_name": "Dc Ammeter 1"
    },

    "DC_I_METER_2": {
        "slave_id": 18,
        "endian": "ABCD",
        "registers": {
            "DC_CURRENT": 0x0BB9,
        },
        "reads": {
            "dc_i": "DC_CURRENT",
        },
        "display_name": "Dc Ammeter 2"
    }

}

logger.info(f"SLAVE_DEVICES configured | Devices={list(SLAVE_DEVICES.keys())}")

# =====================================================
# TEST PARAMETERS
# =====================================================
MIN_IMPEDANCE_MOHM = 1.5

VOLTAGE_TOLERANCE_PERCENT = 20.0
CURRENT_TOLERANCE_PERCENT = 10.0

STABILIZATION_TIME = 1.5

logger.info(
    f"Test tolerances set | "
    f"Voltage={VOLTAGE_TOLERANCE_PERCENT}%, "
    f"Current={CURRENT_TOLERANCE_PERCENT}%"
)
# =====================================================
# QR SCANNER (RAW SERIAL)
# =====================================================

QR_READ_CMD = bytes.fromhex("16 54 0D")
logger.info("QR scanner command configured")

# =====================================================
# DATABASE CONFIG
# =====================================================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "lscontrols",
    "database": "pcb_tester",
    "raise_on_warnings": True
}
logger.info(f"Database configuration loaded | DB={DB_CONFIG['database']}")

# =====================================================
# DROPDOWN OPTIONS
# =====================================================

# === Default Test Cases (33 conditions in the requested format) ===
default_test_cases = [
    {"sn": 1, "desc": "Impedance test b/w R-N, Y-N, B-N)", "r": "NC", "y": "NC", "b": "NC", "n": "NC", "v": "NA",  "i": "NA"},
    {"sn": 2, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 3, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 4, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 5, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 6, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "0A"},
    {"sn": 7, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 8, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 9, "desc": "All 3 Phase input applied", "r": "240V", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "2.5A"},
    {"sn": 10, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V", "i": "0A"},
    {"sn": 11, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 12, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 13, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "2.5A"},
    {"sn": 14, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "0A"},
    {"sn": 15, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "0.5A"},
    {"sn": 16, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "1.25A"},
    {"sn": 17, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "2.5A"},
    {"sn": 18, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 19, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 20, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 21, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 22, "desc": "Working under voltage variations", "r": "288V", "y": "288V", "b": "288V", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 23, "desc": "Working under voltage variations", "r": "288V", "y": "288V", "b": "288V", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 24, "desc": "Working under voltage variations", "r": "288V", "y": "288V", "b": "288V", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 25, "desc": "Working under voltage variations", "r": "288V", "y": "288V", "b": "288V", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 26, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 27, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 28, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 29, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 30, "desc": "Working under voltage variations", "r": "288V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 31, "desc": "Working under voltage variations", "r": "288V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 32, "desc": "Working under voltage variations", "r": "288V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 33, "desc": "Working under voltage variations", "r": "288V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 34, "desc": "Working at higher voltage condition", "r": "500V", "y": "500V", "b": "500V", "n": "NC",  "v": "0V", "i": "1.25A"},
    {"sn": 35, "desc": "Working at higher voltage condition", "r": "510V", "y": "510V", "b": "510V", "n": "NC",  "v": "0V", "i": "1.25A"},
    {"sn": 36, "desc": "Working at higher voltage condition", "r": "520V", "y": "520V", "b": "520V", "n": "NC",  "v": "0V", "i": "1.25A"},
    {"sn": 37, "desc": "Working at higher voltage condition", "r": "530V", "y": "530V", "b": "530V", "n": "NC",  "v": "0V", "i": "1.25A"},

]


# =====================================================
# LOGGING
# =====================================================
def setup_logging():
    log_filename = f"logs/test_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format="%(asctime)s - %(message)s"
    )

    logger.info(f"Legacy logging initialized | File={log_filename}")
    return log_filename

# =====================================================
# AUTO-GENERATED PLC COILS (FROM VOLTAGE_TAPPINGS)
# =====================================================

# =====================================================
# AUTO-GENERATED PLC COILS
# =====================================================



