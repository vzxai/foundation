"""The edit: every shot, generative scene, caption and footnote, in timeline seconds.

Shot fields
  t, d      start and duration on the timeline
  src, at   source film key (footage/films.json) and in-point in seconds, or src="gen:<name>"
  speed     playback rate (0.5 = half-speed), rev reverses the clip
  look      colour treatment (see render.LOOKS)
  zoom      (start, end) scale for a slow push, fit=True pillarboxes instead of cropping
  xf        crossfade-in duration from the previous layer
  blend     how the layer meets what is under it: normal, screen, difference
  fx        per-shot effects: glitch, crush, freeze, invert, feedback
  over      a generative overlay screened on top, as ("loop", params)
"""

HB = 0.375  # beat at 160 BPM
B = 0.75    # beat at 80 BPM


def S(t, d, src, at=0.0, **kw):
    return dict(t=round(t, 4), d=round(d, 4), src=src, at=at, **kw)


def G(t, d, name, **params):
    return dict(t=round(t, 4), d=round(d, 4), src="gen:" + name, params=params)


SHOTS = []
TEXT = []
# sources with burned-in marks to crop away wherever they are used (ffmpeg crop, before scaling)
SOURCE_CROP = {"GSFC_20170412_Lights_m12573_EarthAtNight": "crop=iw*0.82:ih*0.82:iw*0.09:ih*0.12,"}  # (t_in, t_out, style, text)


def text(t0, t1, style, s):
    TEXT.append((t0, t1, style, s))


# ===================================================== I. NOISE  0-48
SHOTS += [
    G(0, 7.5, "flow", order=(0.0, 0.55)),
    S(7, 6, "Wheat_Rush", 2, speed=0.6, look="dust", xf=1.0, zoom=(1.0, 1.06)),
    S(13, 6, "jsc2019m000806_Hurricane_Dorian_190902", 8, look="dust", xf=0.6, zoom=(1.0, 1.05)),
    S(19, 4, "Water1953", 18.5, look="dust", xf=0.4),
    S(23, 4, "Journeyt1967", 401, look="dust", xf=0.4),
    S(27, 4, "Wheat_Rush", 58, speed=0.6, look="dust", xf=0.4),
    G(31, 6.5, "flow", order=(0.6, 1.0), seed=8),
    S(37, 4, "jsc2019m000806_Hurricane_Dorian_190902", 96, look="dust", xf=0.5, zoom=(1.0, 1.1)),
    S(41, 3.5, "Water1953", 126, look="amber", xf=0.4),
    S(44.5, 3.5, "Developm1920", 99, speed=0.7, look="amber", xf=0.4),
]
text(6.0, 12.0, "poem", "winds emerge out of noise")
text(15.0, 21.0, "poem", "the primordial stage of being")
text(20.0, 31.0, "foot", "HEGEL · Science of Logic · 1812|pure being and pure nothing are the same. their truth is becoming: the vanishing of each into the other.")
text(31.5, 37.0, "poem", "a wind is not a thing added to the air.|it is a pattern the air is doing.")
text(39.0, 46.5, "poem", "fiction and creation are one")

# ===================================================== II. COMPRESSION  48-108
SHOTS += [
    S(48, 6, "Developm1920", 112, speed=0.6, look="amber", xf=0.8, zoom=(1.0, 1.08)),
    S(54, 4, "Developm1920", 154, look="amber", xf=0.5),
    S(58, 4, "SpringCo1952", 73, look="natural", xf=0.5),
    G(62, 12, "compression", src="Developm1920", at=196),
    S(74, 4, "SpringCo1952", 386, look="natural", xf=0.5),
    S(78, 4, "Developm1920", 561, look="amber", xf=0.4),
    S(82, 4, "Water1953", 136, look="amber", xf=0.4),
    G(86, 6, "rd"),
    S(92, 4, "SpringCo1952", 313, look="natural", xf=0.5),
    S(96, 4, "Journeyt1967", 433, look="natural", xf=0.5, zoom=(1.0, 1.06)),
    S(100, 4, "Developm1920", 701, look="amber", xf=0.5),
    S(104, 4, "GSFC_20170211_SDO_m12500_Year7", 45, look="natural", xf=0.5, zoom=(1.0, 1.15),
      crop="crop=iw*0.56:ih:0:0,"),
]
text(50.0, 55.0, "poem", "a hallucinated universe")
text(55.5, 61.0, "poem", "a hyperstitioned universe")
text(63.0, 69.0, "poem", "compression as the mechanism of emergence")
text(69.0, 74.0, "poem", "the creator of identity")
text(65.0, 73.5, "math", "Z = f(X)\nP(Zₜ₊₁ | Xₜ, aₜ) ≈ P(Zₜ₊₁ | Zₜ, aₜ)")
text(74.0, 86.0, "foot", "SCHMIDHUBER · Formal Theory of Creativity · 1990–2010|beauty is compressibility. interest is compression progress: the moment a pattern becomes simpler to describe, it becomes visible as something.")
text(76.0, 82.0, "poem", "an identity is a compression that still predicts its own future")
text(87.0, 92.0, "poem", "fiction as beauty")
text(92.0, 104.0, "foot", "KANT · Critique of Judgment · 1790|purposiveness without purpose: we recognize a form as organized before we know what it is for.")

# ===================================================== III. RHIZOME / TERRITORY  108-162
SHOTS += [
    G(108, 6, "rhizome", grow=(0, 6), snap=(99, 100)),
    S(114, 4, "ATripDownMarketStreet_HD", 72, look="silver", xf=0.3),
    S(118, 4, "ATripDownMarketStreet_HD", 192, look="silver"),
    S(122, 4, "GSFC_20170412_Lights_m12573_EarthAtNight", 42, look="natural", xf=0.3),
    G(126, 6, "rhizome", grow=(-1, 0), snap=(0.5, 5.0)),
    S(132, 3, "CityTheP1939", 736, look="silver"),
    S(135, 3, "CityTheP1939", 800, look="silver"),
    S(138, 3, "MasterHa1936_2", 180, look="silver"),
    S(141, 3, "MasterHa1936_3", 50, look="silver"),
    S(144, 3, "OurHomeT1954_2", 294, look="silver"),
    S(147, 3, "Typesett1960", 782, look="silver"),
    S(150, 3, "MasterHa1936_2", 300, look="silver"),
    S(153, 3, "Freedomo1955", 736, look="silver"),
    S(156, 1.5, "MasterHa1936_3", 80, look="silver"),
    S(157.5, 1.5, "Typesett1960", 442, look="silver"),
    S(159, 0.75, "big_board", 60, look="silver"),
    S(159.75, 0.75, "Century21964", 390, look="silver"),
    S(160.5, 0.375, "logic_by_machine_1", 416, look="silver"),
    S(160.875, 0.375, "MasterHa1936_3", 295, look="silver"),
    S(161.25, 0.375, "CityTheP1939", 720, look="silver"),
    S(161.625, 0.375, "MasterHa1936_2", 24, look="silver", fx=["invert"]),
]
text(109.0, 114.0, "poem", "the universe is a rhizomatic structure")
text(112.0, 124.0, "foot", "DELEUZE & GUATTARI · A Thousand Plateaus · 1980|a rhizome has no center: any point can be connected to any other. territory captures its flows and gives them a code.")
text(127.0, 132.0, "poem", "yet it can be territorialized")
text(138.0, 143.5, "poem", "being becomes an appendage of a totality")
text(140.0, 150.0, "foot", "MARX · Manifesto of the Communist Party · 1848|“he becomes an appendage of the machine.”")
text(150.0, 155.0, "poem", "its flows reoriented")

# ===================================================== IV. TECHNOCAPITAL  162-228 (160 BPM)
T4 = 162.0
verse = [("Designfo1956", 72), ("big_board", 36), ("Designfo1956", 135), ("Century21964", 26),
         ("ClassicT1948_6", 112), ("Designfo1956", 387), ("big_board", 708), ("Designfo1956", 504)]
for k, (src, at) in enumerate(verse):
    SHOTS.append(S(T4 + k * 4 * HB, 4 * HB, src, at, look="neon"))
SHOTS += [
    S(174, 6, "big_board", 38, look="neon", speed=0.5, over=("loop", {})),
    S(180, 1.5, "Century21964", 416, look="neon"),
    S(181.5, 1.5, "logic_by_machine_1", 377, look="neon"),
    S(183, 1.5, "Typesett1960", 34, look="neon"),
    S(184.5, 1.5, "big_board", 288, look="neon"),
]
POOL = [("Designfo1956", 0), ("Designfo1956", 72), ("Designfo1956", 81), ("Designfo1956", 126),
        ("Designfo1956", 162), ("Designfo1956", 261), ("Designfo1956", 315), ("Designfo1956", 324),
        ("Designfo1956", 378), ("Designfo1956", 405), ("Designfo1956", 423), ("Designfo1956", 432),
        ("Designfo1956", 486), ("Designfo1956", 522), ("big_board", 36), ("big_board", 60),
        ("big_board", 276), ("big_board", 444), ("big_board", 492), ("big_board", 636),
        ("big_board", 648), ("big_board", 660), ("big_board", 708), ("Century21964", 26),
        ("Century21964", 78), ("Century21964", 208), ("Century21964", 364), ("Century21964", 390),
        ("Century21964", 507), ("ClassicT1948_6", 84), ("ClassicT1948_6", 112), ("ClassicT1948_6", 392),
        ("isforAto1953", 56), ("isforAto1953", 70), ("isforAto1953", 140), ("isforAto1953", 434),
        ("isforAto1953", 462), ("OurHomeT1954_2", 882), ("OurHomeT1954_2", 1008), ("Freedomo1955", 192),
        ("Freedomo1955", 208), ("Freedomo1955", 896), ("logic_by_machine_1", 377), ("logic_by_machine_1", 390),
        ("Typesett1960", 442), ("Typesett1960", 782), ("GSFC_20170412_Lights_m12573_EarthAtNight", 26)]


def pick(k, jitter=0.0):
    src, at = POOL[(k * 7 + 3) % len(POOL)]
    return src, at + (k % 5) * 0.4 + jitter


# build: accelerating cuts
k = 0
t = 186.0
while t < 192 - 1e-6:
    d = HB if t < 189 else HB / 2
    src, at = pick(k)
    SHOTS.append(S(t, d, src, at, look="neon", fx=["glitch"] if t > 189 else []))
    t += d
    k += 1
# drop: three cuts a bar, then four-on-the-floor cuts on every beat
for bar in range(16):
    tb = 192 + bar * 4 * HB
    for off, d in ((0, 2 * HB), (2 * HB, HB), (3 * HB, HB)):
        src, at = pick(k)
        SHOTS.append(S(tb + off, d, src, at, look="neon", fx=["glitch"]))
        k += 1
for beat in range(28):
    src, at = pick(k)
    SHOTS.append(S(216 + beat * HB, HB, src, at, look="neon", fx=["glitch", "crush"] if beat % 4 == 3 else ["glitch"]))
    k += 1
SHOTS += [
    S(226.5, 1.5, "KSC-20230507-MH-RLS01-TROPICS_Rocket_Launch-Rocket_Lab-WON_3330130", 16, look="neon",
      fx=["glitch", "freeze"], speed=0.25),
]
for k, w in enumerate(["CAPITAL", "IS", "A", "HYPERSTITIONAL", "ENGINE"]):
    text(T4 + 1.5 + k * 2 * HB, T4 + 1.5 + (k + 1) * 2 * HB, "hp", w)
text(163.5, 175.0, "foot", "LAND / CCRU · 1990s|hyperstition: a positive feedback circuit including culture as a component. fictions that make themselves real.")
text(174.0, 177.0, "poem", "capitalism is a hyperstitional engine")
text(177.0, 180.0, "poem", "a system for organizing totality")
text(180.0, 183.0, "poem", "in its own self-learned, emergent way")
text(183.0, 186.0, "poem", "fiction that makes itself real")
text(186.0, 189.0, "hp_small", "HUMANITY AT THE BEHEST OF TECHNOCAPITAL")
text(189.0, 192.0, "hp_small", "THE ULTIMATE FORM OF ENTROPY?")
LOOPWORDS = ["EXPECTED RETURNS", "→ INVESTMENT", "→ INFRASTRUCTURE", "→ EXPECTATION"]
for bar in range(16):
    if bar % 4 in (0, 2):
        w = LOOPWORDS[(bar // 2) % 4]
        text(192 + bar * 4 * HB, 192 + (bar + 1) * 4 * HB, "hp", w)
text(198.0, 212.0, "foot", "FISHER · Capitalist Realism · 2009|“it is easier to imagine the end of the world than the end of capitalism.” (after Jameson and Žižek)")
text(216.0, 226.0, "foot", "BEER · cybernetics · 1970s–2000s|the purpose of a system is what it does.")
for k, w in enumerate(["IT", "LEARNS", "ITSELF", "INTO", "THE", "FUTURE"]):
    text(216 + k * 4 * HB, 216 + (k + 0.6) * 4 * HB, "hp", w)

# ===================================================== V. METABOLISM  228-282
# deconstruction: fragments of the engine's footage, stuttered and broken on the score's hits
SHOTS += [S(228, 2, "gen:black", 0)]
decon = [(230.0, 1.2, ("Designfo1956", 135), ["freeze", "crush"]), (231.2, 0.8, ("big_board", 60), ["glitch"]),
         (232.0, 1.5, ("Designfo1956", 72), ["feedback"]), (233.5, 1.0, ("Century21964", 390), ["invert"]),
         (234.5, 2.0, ("isforAto1953", 462), ["feedback", "glitch"]), (236.5, 0.75, ("big_board", 708), ["crush"]),
         (237.25, 0.75, ("Designfo1956", 504), ["freeze"]), (238.0, 2.5, ("ATripDownMarketStreet_HD", 72), ["feedback"]),
         (240.5, 1.0, ("Designfo1956", 315), ["glitch", "invert"]), (241.5, 1.5, ("big_board", 36), ["feedback"]),
         (243.0, 3.0, ("GSFC_20170412_Lights_m12573_EarthAtNight", 30), ["feedback", "glitch"])]
for t, d, (src, at), fx in decon:
    SHOTS.append(S(t, d, src, at, look="acid", fx=fx, rev="freeze" not in fx and t % 2 > 1, speed=0.5))
# metabolism: life footage and engine footage in double exposure
SHOTS += [
    S(246, 3, "Developm1920", 140, look="amber", speed=0.7),
    S(246, 3, "Designfo1956", 135, look="acid", blend="screen", alpha=0.6),
    S(249, 3, "SpringCo1952", 386, look="natural"),
    S(249, 3, "big_board", 36, look="acid", blend="difference", alpha=0.7),
    S(252, 3, "Developm1920", 700, look="amber"),
    S(252, 3, "isforAto1953", 392, look="acid", blend="screen", alpha=0.6),
    S(255, 3, "jsc2019m000806_Hurricane_Dorian_190902", 130, look="acid", fx=["feedback"]),
    S(258, 6, "logic_by_machine_1", 468, look="silver", zoom=(1.0, 1.08)),
    S(264, 8, "KSC-20230507-MH-RLS01-TROPICS_Rocket_Launch-Rocket_Lab-WON_3330130", 12, look="natural", speed=0.5),
    S(272, 6, "GSFC_20170412_Lights_m12573_EarthAtNight", 4, look="natural", fx=["feedback"], speed=0.5),
    S(278, 4, "gen:white", 0),
]
text(228.3, 232.0, "poem_big", "yet this is not the only possibility")
text(234.0, 245.0, "foot", "BEER · Viable System Model · 1972–79|recursion: any viable system contains, and is contained in, a viable system.")
text(246.2, 249.0, "poem", "recursive memetic structures")
text(249.2, 252.0, "poem", "may produce cultural foom")
text(252.2, 255.0, "poem", "a way to metabolize")
text(255.2, 258.0, "poem", "the singularity")
text(258.5, 264.0, "foot", "HAMMING · 1962|the purpose of computing is insight, not numbers.")
text(264.0, 271.5, "foot", "NOTE|a conspiracy spreads. a bubble spreads. a science spreads. recursion becomes intelligence only when it learns from what resists it.")
text(272.0, 278.0, "foot", "FOOM · Yudkowsky–Hanson debate · 2008|a runaway of self-improving intelligence. here: a culture that learns faster than the engine that captured it.")

# ===================================================== VI. SINGLETON  282-339
VENN = [("Journeyt1967", 496, "V₁"), ("logic_by_machine_1", 377, "V₂"),
        ("SpringCo1952", 73, "V₃"), ("Century21964", 78, "V₄")]
SHOTS += [
    S(282, 6, "Journeyt1967", 352, look="gold", xf=0.0, zoom=(1.0, 1.06)),
    S(288, 6, "ClassicT1948_6", 196, look="gold", xf=0.6),
    G(294, 12, "venn", srcs=VENN, phase="meet"),
    S(306, 4, "Journeyt1967", 496, look="gold", xf=0.5),
    S(310, 4, "SpringCo1952", 696, look="gold", xf=0.5),
    G(314, 6, "venn", srcs=VENN, phase="expand"),
    S(320, 4, "Century21964", 78, look="gold", xf=0.5),
    S(324, 4, "Journeyt1967", 560, look="gold", xf=0.5),
    S(328, 4, "jsc2019m000806_Hurricane_Dorian_190902", 10, look="gold", xf=0.5),
    S(332, 7, "GSFC_20170412_Lights_m12573_EarthAtNight", 11.5, look="natural", xf=0.6, zoom=(1.0, 1.12), speed=0.6),
]
text(282.1, 287.8, "poem", "what if the purpose of collective intelligence")
text(288.1, 293.8, "poem", "is not to discover one perfect future")
text(294.1, 299.8, "poem", "but to expand the region of futures")
text(300.1, 305.8, "poem", "in which different forms of being")
text(306.1, 311.8, "poem", "can coexist and flourish")
text(297.0, 305.8, "math", "S = V₁ ∩ V₂ ∩ V₃ ∩ V₄")
text(312.1, 319.5, "poem_big", "this is where we must strive to be")
text(306.5, 318.0, "foot", "THE SINGLETON SET|in the set of beings that emerge there is an intersection that provides mutual benefit. it may be large, small, or empty. it can be grown.")
text(320.0, 332.0, "foot", "KANT · Groundwork of the Metaphysics of Morals · 1785|a kingdom of ends: a union of beings who treat one another never merely as means.")

# ===================================================== VII. CODA  339-360
SHOTS += [
    S(339, 8, "Wheat_Rush", 44, speed=0.5, look="dust", xf=1.0),
    G(346, 14, "flow", order=(1.0, 0.0), seed=8),
]
text(345.0, 351.0, "poem", "fiction is infrastructure")
text(352.0, 358.0, "title", "WINDS OUT OF NOISE")

# per-section treatment: grain amount and whether beats flash the picture
SECTION_STYLE = {
    "I": dict(grain=0.10, flash=0.0), "II": dict(grain=0.07, flash=0.0),
    "III": dict(grain=0.08, flash=0.15), "IV": dict(grain=0.06, flash=0.35),
    "V": dict(grain=0.09, flash=0.25), "VI": dict(grain=0.05, flash=0.0),
    "VII": dict(grain=0.10, flash=0.0),
}
