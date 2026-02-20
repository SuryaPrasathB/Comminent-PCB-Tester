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
    "baudrate": 9600,  # CHANGE if required
    "parity": "N",  # 'N', 'E', 'O'
    "stopbits": 1,
    "bytesize": 8,
    "timeout": 1.0,  # seconds
    "exclusive": True  # IMPORTANT for Windows
}

logger.info("SERIAL_SETTINGS loaded")

NEUTRAL_OPTIONS  = ["NC", "C"]
#VOLTAGE_TAPPINGS = ["NC", "138V", "144V", "240V", "265V", "500V", "510V", "520V", "530V"]
VOLTAGE_TAPPINGS = ["530V", "520V", "510V", "500V", "460V", "240V", "144V", "138V", "NC"]
CURRENT_TAPPINGS = ["0A", "0.5A", "1.25A", "2.5A"]

VLL_TO_TAP = {
    "530V": "306",
    "520V": "300",
    "510V": "295",
    "500V": "288",
    "460V": "265",
    "240V": "138",
}

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
     // Mapped as per Electrical drawing made.
    'MAIN_CONTACTOR' : 1,
    //=====================
    // Transformer tapping - For all 3 phases (R, Y, B) =================
    'T_306': 2,  // VLL = 530
    'T_300': 3,  // VLL = 520
    'T_295': 4,  // VLL = 510
    'T_288': 5,  // VLL = 500
    'T_265': 6,
    'T_240': 7,
    'T_144': 8,
    'T_138': 9,   // VLL = 240
    //==========================
    'R_EN = 10,
    'Y_EN = 11,
    'B_EN = 12,
    //==========================
    'PCB_2_EN' : 13,
    'NEUTRAL'  : 14,
    //==========================
    'IMP1_R'   : 15,   // 1st PCB
    'IMP1_Y'   : 16,   // 1st PCB
    'IMP1_B'   : 17    // 1st PCB
    'IMP1_N'   : 18    // 1st PCB
    
    'IMP2_R'   : 19,   // 2nd PCB
    'IMP2_Y'   : 20,   // 2nd PCB
    'IMP2_B'   : 21    // 2nd PCB                                                                                                                                        
    'IMP2_N'   : 22    // 2nd PCB
    //==========================
    'CUR1_0_5' :  23, // 1st PCB
    'CUR1_1_25':  24, // 1st PCB
    'CUR1_2_5' :  25, // 1st PCB

    'CUR2_0_5' :  26, // 2nd PCB
    'CUR2_1_25':  27, // 2nd PCB
    'CUR2_2_5' :  28, // 2nd PCB
    //==========================
    'IMP1_TEST_EN': 29,  // 1st PCB
    'IMP2_TEST_EN': 30,  // 2nd PCB
    //==========================
    'ALARM' : 31
    //=========================


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

    # =======================================================
    # Main Contactor
    coils["MAIN_CONTACTOR"] = addr
    addr += 1

    # =======================================================
    # Transformer tapping (COMMON for R/Y/B)
    # Order: High → Low (as per electrical drawing)

    tap_keys = []

    for tap in voltage_tappings:
        if tap == "NC":
            continue

        # High voltage taps must use mapped values only
        if tap in VLL_TO_TAP:
            mapped_key = VLL_TO_TAP[tap]
            if mapped_key not in tap_keys:
                tap_keys.append(mapped_key)

            # Special case:
            # 240V also needs direct tap
            if tap == "240V" and "240" not in tap_keys:
                tap_keys.append("240")

        else:
            direct_key = tap.replace("V", "")
            if direct_key not in tap_keys:
                tap_keys.append(direct_key)

    # ---- Sort as per electrical drawing (High → Low) ----
    tap_keys = sorted(tap_keys, key=lambda x: int(x), reverse=True)

    # ---- Assign addresses ----
    for tap_key in tap_keys:
        coils[f"T_{tap_key}"] = addr
        addr += 1

    # =======================================================
    # Phase enable contactors
    coils["R_EN"] = addr; addr += 1
    coils["Y_EN"] = addr; addr += 1
    coils["B_EN"] = addr; addr += 1

    # =======================================================
    # PCB selection & Neutral
    coils["PCB_2_EN"] = addr
    addr += 1

    coils["NEUTRAL"] = addr
    addr += 1

    # =======================================================
    # Impedance relays – PCB 1
    for phase in ("R", "Y", "B", "N"):
        coils[f"IMP1_{phase}"] = addr
        addr += 1

    # =======================================================
    # Impedance relays – PCB 2
    for phase in ("R", "Y", "B", "N"):
        coils[f"IMP2_{phase}"] = addr
        addr += 1

    # =======================================================
    # Current selection – PCB 1 & PCB 2
    for pcb in (1, 2):
        for cur in current_tappings:
            if cur == "0A":
                continue
            cur_key = cur.replace("A", "").replace(".", "_")
            coils[f"CUR{pcb}_{cur_key}"] = addr
            addr += 1

    # =======================================================
    # Impedance test enable
    coils["IMP1_TEST_EN"] = addr
    addr += 1

    coils["IMP2_TEST_EN"] = addr
    addr += 1

    # =======================================================
    # Alarm
    coils["ALARM"] = addr
    addr += 1

    # =======================================================
    # Start Input
    coils["START"] = 35

    # Safety Inputs (Fixed Addresses)
    coils["PCB"] = 102
    coils["EMERGENCY_STOP"] = 104
    coils["CURTAIN_SENSOR"] = 103

    # =======================================================
    # PRINT SUMMARY
    print("\n--- PLC COIL MAP (SUMMARY) ---")
    for name, address in sorted(coils.items(), key=lambda x: x[1]):
        print(f"{address:04d} : {name}")

    print("\n//=======================================================\n")
    print(f"Total coils generated: {len(coils)}")

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
        "read_cmd": "025404",  # in Hex
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
            "R_N_VOLTAGE": 0x008E,
            "Y_N_VOLTAGE": 0x0090,
            "B_N_VOLTAGE": 0x0092,
            "R_Y_VOLTAGE": 0x0086,
            "Y_B_VOLTAGE": 0x0088,
            "B_R_VOLTAGE": 0x008A,
        },
        "reads": {
            "r_n_v": "R_N_VOLTAGE",
            "y_n_v": "Y_N_VOLTAGE",
            "b_n_v": "B_N_VOLTAGE",
            "r_y_v": "R_Y_VOLTAGE",
            "y_b_v": "Y_B_VOLTAGE",
            "b_r_v": "B_R_VOLTAGE",
        },
        "display_name": "Ac Meter"
    },

    "IMP_METER_1": {
        "slave_id": 4,
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
        "slave_id": 3,
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
        "slave_id": 18,
        "endian": "ABCD",
        "registers": {
            "DC_VOLTAGE": 0x0BB7,
        },
        "reads": {
            "dc_v_1": "DC_VOLTAGE",
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
            "dc_v_2": "DC_VOLTAGE",
        },
        "display_name": "Dc Voltmeter 2"
    },

    "DC_I_METER_1": {
        "slave_id": 18,
        "endian": "ABCD",
        "registers": {
            "DC_CURRENT": 0x0BB9,
        },
        "reads": {
            "dc_i_1": "DC_CURRENT",
        },
        "display_name": "Dc Ammeter 1"
    },

    "DC_I_METER_2": {
        "slave_id": 17,
        "endian": "ABCD",
        "registers": {
            "DC_CURRENT": 0x0BB9,
        },
        "reads": {
            "dc_i_2": "DC_CURRENT",
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
CURRENT_TOLERANCE_PERCENT = 20.0

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
    {"sn": 11, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "240V", "n": "NC", "v": "5V", "i": "0A"},
    {"sn": 12, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "240V", "n": "NC", "v": "5V", "i": "0A"},
    {"sn": 13, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 14, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 15, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "240V", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 16, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 17, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 18, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "240V", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 19, "desc": "Working on any 2 wires", "r": "240V", "y": "240V", "b": "NC", "n": "NC", "v": "5V",  "i": "2.5A"},
    {"sn": 20, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "240V", "n": "NC", "v": "5V",  "i": "2.5A"},
    {"sn": 21, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "240V", "n": "NC", "v": "5V",  "i": "2.5A"},

    {"sn": 22, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "0A"},
    {"sn": 23, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "0.5A"},
    {"sn": 24, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "1.25A"},
    {"sn": 25, "desc": "Working on any 2 wires", "r": "240V", "y": "NC", "b": "NC", "n": "C", "v": "5V", "i": "2.5A"},

    {"sn": 26, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "NC", "n": "C", "v": "5V", "i": "0A"},
    {"sn": 27, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "NC", "n": "C", "v": "5V", "i": "0.5A"},
    {"sn": 28, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "NC", "n": "C", "v": "5V", "i": "1.25A"},
    {"sn": 29, "desc": "Working on any 2 wires", "r": "NC", "y": "240V", "b": "NC", "n": "C", "v": "5V", "i": "2.5A"},

    {"sn": 30, "desc": "Working on any 2 wires", "r": "NC", "y": "NC", "b": "240V", "n": "C", "v": "5V", "i": "0A"},
    {"sn": 31, "desc": "Working on any 2 wires", "r": "NC", "y": "NC", "b": "240V", "n": "C", "v": "5V", "i": "0.5A"},
    {"sn": 32, "desc": "Working on any 2 wires", "r": "NC", "y": "NC", "b": "240V", "n": "C", "v": "5V", "i": "1.25A"},
    {"sn": 33, "desc": "Working on any 2 wires", "r": "NC", "y": "NC", "b": "240V", "n": "C", "v": "5V", "i": "2.5A"},

    {"sn": 34, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 35, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 36, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 37, "desc": "Working under voltage variations", "r": "144V", "y": "144V", "b": "144V", "n": "C", "v": "5V",  "i": "2.5A"},
    {"sn": 38, "desc": "Working under voltage variations", "r": "500V", "y": "500V", "b": "500V", "n": "NC", "v": "0V",  "i": "0A"},
    {"sn": 39, "desc": "Working under voltage variations", "r": "500V", "y": "500V", "b": "500V", "n": "NC", "v": "0V",  "i": "0A"},
    {"sn": 40, "desc": "Working under voltage variations", "r": "500V", "y": "500V", "b": "500V", "n": "NC", "v": "0V",  "i": "0A"},
    {"sn": 41, "desc": "Working under voltage variations", "r": "500V", "y": "500V", "b": "500V", "n": "NC", "v": "0V",  "i": "0A"},
    
    {"sn": 42, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 43, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 44, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 45, "desc": "Working under voltage variations", "r": "144V", "y": "NC", "b": "NC", "n": "C", "v": "5V",  "i": "2.5A"},

    {"sn": 46, "desc": "Working under voltage variations", "r": "NC", "y": "144V", "b": "NC", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 47, "desc": "Working under voltage variations", "r": "NC", "y": "144V", "b": "NC", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 48, "desc": "Working under voltage variations", "r": "NC", "y": "144V", "b": "NC", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 49, "desc": "Working under voltage variations", "r": "NC", "y": "144V", "b": "NC", "n": "C", "v": "5V",  "i": "2.5A"},

    {"sn": 50, "desc": "Working under voltage variations", "r": "NC", "y": "NC", "b": "144V", "n": "C", "v": "5V",  "i": "0A"},
    {"sn": 51, "desc": "Working under voltage variations", "r": "NC", "y": "NC", "b": "144V", "n": "C", "v": "5V",  "i": "0.5A"},
    {"sn": 52, "desc": "Working under voltage variations", "r": "NC", "y": "NC", "b": "144V", "n": "C", "v": "5V",  "i": "1.25A"},
    {"sn": 53, "desc": "Working under voltage variations", "r": "NC", "y": "NC", "b": "144V", "n": "C", "v": "5V",  "i": "2.5A"},

    {"sn": 54, "desc": "Working under voltage variations", "r": "500V", "y": "NC", "b": "NC", "n": "NC", "v": "5V",  "i": "0A"},
    {"sn": 55, "desc": "Working under voltage variations", "r": "500V", "y": "NC", "b": "NC", "n": "NC", "v": "5V",  "i": "0.5A"},
    {"sn": 56, "desc": "Working under voltage variations", "r": "500V", "y": "NC", "b": "NC", "n": "NC", "v": "5V",  "i": "1.25A"},
    {"sn": 57, "desc": "Working under voltage variations", "r": "500V", "y": "NC", "b": "NC", "n": "NC", "v": "5V",  "i": "2.5A"},
    
    {"sn": 58, "desc": "Working at higher voltage condition", "r": "500V", "y": "500V", "b": "500V", "n": "NC", "v": "0V",  "i": "0A"},
    {"sn": 59, "desc": "Working at higher voltage condition", "r": "460V", "y": "460V", "b": "460V", "n": "NC", "v": "0V",  "i": "1.25A"},
    {"sn": 60, "desc": "Working at higher voltage condition", "r": "510V", "y": "510V", "b": "510V", "n": "NC", "v": "0V", "i": "0A"},
    {"sn": 61, "desc": "Working at higher voltage condition", "r": "460V", "y": "460V", "b": "460V", "n": "NC", "v": "0V", "i": "1.25A"},
    {"sn": 62, "desc": "Working at higher voltage condition", "r": "520V", "y": "520V", "b": "520V", "n": "NC", "v": "0V", "i": "0A"},
    {"sn": 63, "desc": "Working at higher voltage condition", "r": "460V", "y": "460V", "b": "460V", "n": "NC","v": "0V", "i": "1.25A"},
    {"sn": 64, "desc": "Working at higher voltage condition", "r": "530V", "y": "530V", "b": "530V", "n": "NC", "v": "0V", "i": "0A"},
    {"sn": 65, "desc": "Working at higher voltage condition", "r": "460V", "y": "460V", "b": "460V", "n": "NC","v": "0V", "i": "1.25A"},

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



