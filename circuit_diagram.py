import io
import schemdraw
import schemdraw.elements as elm
import schemdraw.flow as flow

from logs import logger


# =================================================
# FONT SIZE CONTROLS (YOU CAN TUNE THESE)
# =================================================
PHASE_FONT   = 16     # R / Y / B / N labels
AC_VOLT_FONT = 12     # AC voltage text (240 V / 0 V)
DC_VOLT_FONT = 12     # DC voltage text
DC_CURR_FONT = 12     # DC current text
LOAD_FONT    = 12     # LOAD text


# =================================================
# FORMAT HELPERS
# =================================================
def fmt_v(v):
    try:
        v = float(v)
        return f"{int(v)} V" if v.is_integer() else f"{v} V"
    except Exception:
        logger.warning(f"fmt_v : Invalid voltage value '{v}'")
        return ""


def fmt_i(i):
    try:
        i = float(i)
        return f"{int(i)} A" if i.is_integer() else f"{i} A"
    except Exception:
        logger.warning(f"fmt_i : Invalid current value '{i}'")
        return ""


def fmt_ac_voltage(value):
    """
    If AC input is NC → show 0 V
    Else → show actual voltage
    """
    if value == "NC":
        return "0 V"
    return fmt_v(value)


# =================================================
# MAIN DRAWING FUNCTION
# =================================================
def generate_three_phase_diagram(
    r_voltage,
    y_voltage,
    b_voltage,
    neutral_state,
    dc_voltage,
    dc_current
):
    print("[CD] generate_three_phase_diagram()")
    print(f"r_voltage  : {r_voltage}")
    print(f"y_voltage  : {y_voltage}")
    print(f"b_voltage  : {b_voltage}")
    print(f"dc_voltage : {dc_voltage}")
    print(f"dc_current : {dc_current}")

    logger.info(
        f"generate_three_phase_diagram called | "
        f"R={r_voltage}, Y={y_voltage}, B={b_voltage}, "
        f"N={neutral_state}, DC_V={dc_voltage}, DC_I={dc_current}"
    )

    # -------------------------------------------------
    # DRAWING SCALE (balanced)
    # -------------------------------------------------
    d = schemdraw.Drawing(unit=2.0, inches_per_unit=0.6)
    d.config(fontsize=PHASE_FONT)

    logger.info("Schemdraw canvas initialized")

    # =================================================
    # AC INPUTS + SWITCHES
    # =================================================

    # ---------- R PHASE ----------
    d.add(
        elm.Line()
        .right(2)
        .label("R", loc="left", fontsize=PHASE_FONT)
        .label(fmt_ac_voltage(r_voltage), loc="top", fontsize=AC_VOLT_FONT)
    )
    d.add(elm.Switch(nc=(r_voltage != "NC")).right(1))
    d.add(elm.Line().right(2))

    # ---------- Y PHASE ----------
    d.add(
        elm.Line()
        .right(2)
        .at((0, -1.5))
        .label("Y", loc="left", fontsize=PHASE_FONT)
        .label(fmt_ac_voltage(y_voltage), loc="top", fontsize=AC_VOLT_FONT)
    )
    d.add(elm.Switch(nc=(y_voltage != "NC")).right(1))
    d.add(elm.Line().right(2))

    # ---------- B PHASE ----------
    d.add(
        elm.Line()
        .right(2)
        .at((0, -3.0))
        .label("B", loc="left", fontsize=PHASE_FONT)
        .label(fmt_ac_voltage(b_voltage), loc="top", fontsize=AC_VOLT_FONT)
    )
    d.add(elm.Switch(nc=(b_voltage != "NC")).right(1))
    d.add(elm.Line().right(2))

    # ---------- NEUTRAL ----------
    d.add(
        elm.Line()
        .right(2)
        .at((0, -4.5))
        .label("N", loc="left", fontsize=PHASE_FONT)
    )
    d.add(elm.Switch(nc=(neutral_state != "NC")).right(1))
    d.add(elm.Line().right(2))

    logger.info("AC inputs and neutral drawn")

    # =================================================
    # PCB BLOCK
    # =================================================
    d.add(flow.Box(w=3, h=6).at((5, -2.25)).label("PCB"))

    for y, lbl in zip([0, -1.5, -3.0, -4.5], ["R", "Y", "B", "N"]):
        d.add(flow.Box(w=0.5, h=0.5).at((5, y)).label(lbl))

    logger.info("PCB block drawn")

    # =================================================
    # DC OUTPUT TERMINALS (+ / -)
    # =================================================
    d.add(flow.Box(w=-0.5, h=0.5).at((8, -1.0)).label("+"))
    d.add(flow.Box(w=-0.5, h=0.5).at((8, -3.5)).label("-"))

    # =================================================
    # DC RAILS TO LOAD (HORIZONTAL)
    # =================================================
    d.add(elm.Line().right(3).at((8, -1.0)))    # + rail
    d.add(elm.Line().right(3).at((8, -3.5)))    # - rail

    # =================================================
    # DC CURRENT INDICATOR (PLUG SYMBOL)
    # =================================================
    d.add(
        elm.Plug()
        .scale(0.5)
        .at((9.2, -1.0))
    )
    d.add(
        elm.Label()
        .at((9.5, -0.7))
        .label(fmt_i(dc_current), fontsize=DC_CURR_FONT)
    )

    # =================================================
    # VERTICAL DROPS INTO LOAD
    # =================================================
    d.add(elm.Line().down(0.45).at((11, -1.0)))
    d.add(elm.Line().up(0.45).at((11, -3.5)))

    # =================================================
    # LOAD
    # =================================================
    d.add(
        flow.Box(w=0.5, h=1.5)
        .at((11, -3))
        .label("LOAD", rotate=90, fontsize=LOAD_FONT)
    )

    # =================================================
    # DC VOLTAGE ACROSS LOAD
    # =================================================
    d.add(
        elm.Label()
        .at((11.9, -2.25))
        .label(fmt_v(dc_voltage), fontsize=DC_VOLT_FONT)
    )

    # =================================================
    # RENDER TO MEMORY (UI SAFE)
    # =================================================
    # Generate SVG data
    svg_bytes = d.get_imagedata("svg")

    # Decode to string for manipulation
    svg_str = svg_bytes.decode("utf-8")

    # Post-process SVG to ensure responsiveness and centering
    # Use regex to find the opening <svg ...> tag to avoid modifying child elements like <rect width="...">
    import re
    match = re.search(r'<svg[^>]*>', svg_str)
    if match:
        tag = match.group(0)

        # Ensure preserveAspectRatio is present
        if "preserveAspectRatio" not in tag:
            # We insert it after the opening <svg part
            # A safe way is to replace "<svg" with "<svg preserveAspectRatio='...'"
            # taking care if attributes follow immediately.
            new_tag = tag.replace("<svg", '<svg preserveAspectRatio="xMidYMid meet"', 1)
        else:
            new_tag = tag

        # Replace the old tag with the new tag in the SVG string
        svg_str = svg_str.replace(tag, new_tag, 1)

    data = svg_str.encode("utf-8")
    print(f"[CD] SVG bytes generated: {len(data)}")

    logger.info(f"Three-phase diagram rendered | SVG bytes={len(data)}")

    return data
