"""Per-version facts of the two EXE5 revisions, measured on these ROMs.

Every address here was found on the target ROM (README "대사 렌더 경로");
Colonel is not derived from Blues by a delta. `expected` bytes are checked
before any write, so a different input fails instead of being patched blind.
"""

PROFILES = {
    "blues": {
        "rom_name": "Rockman EXE 5 - Team of Blues (Japan).gba",
        "sha256": "284ae3c7c9d3b6eaaf8ed858f33de91a62b0bcf66d04cf21d6838d042b83a4ab",
        "font": 0x6D7B5C,
        "width": 0x425C0,
        # IWRAM code is copied from ROM 0x1C7A00 to 0x03005C00 at boot.
        "font_literals": [0x1C9030, 0x1C90C4],
        "width_literals": [0x1C9038, 0x1C90CC],
        "fa_slot": 0x3F890,          # control table 0x3F83C, index FA-E5
        "fa_legacy": 0x08040969,
        "renderer": 0x03007199,
        "flag_set": 0x0803F3A1,
        "flag_clear": 0x0803F3AD,
        "flag_test": 0x0803F3B9,
        "sound": 0x08000599,
        "mouth": 0x0803F6B1,
        "ctrl_done": 0x0803F705,
        "cont_normal": 0x0803EA39,
        "cont_fast": 0x0803EB29,
    },
    "colonel": {
        "rom_name": "Rockman EXE 5 - Team of Colonel (Japan).gba",
        "sha256": "c066880ffd7c668afe0824000eedf7266c4b91aa22092838db4566564bbbddfd",
        "font": 0x6D8FF0,
        "width": 0x425C8,
        "font_literals": [0x1C9034, 0x1C90C8],
        "width_literals": [0x1C903C, 0x1C90D0],
        "fa_slot": 0x3F894,
        "fa_legacy": 0x08040971,
        "renderer": 0x0300719D,
        "flag_set": 0x0803F3A5,
        "flag_clear": 0x0803F3B1,
        "flag_test": 0x0803F3BD,
        "sound": 0x08000599,
        "mouth": 0x0803F6B5,
        "ctrl_done": 0x0803F709,
        "cont_normal": 0x0803EA3D,
        "cont_fast": 0x0803EB2D,
    },
}

# Code bytes each hook target must start with (Thumb, little endian), so a
# wrong address cannot be called silently. Same in both versions.
FUNCTION_SIGNATURES = {
    "flag_set": "02b4e98f0143",      # push {r1}; ldrh r1,[r5,#0x3e]; orrs r1,r0
    "flag_clear": "02b4e98f8143",    # ... bics r1,r0
    "flag_test": "02b4e98f0840",     # ... ands r0,r1
    "mouth": "33b51020",             # push {r0,r1,r4,r5,lr}; movs r0,#0x10
    "ctrl_done": "03b50020",         # push {r0,r1,lr}; movs r0,#0
    "cont_normal": "ec620042",       # str r4,[r5,#0x2c]; tst r0,r0
    "cont_fast": "ec62ea8f",         # str r4,[r5,#0x2c]; ldrh r2,[r5,#0x3e]
    "renderer": "f2b54746",          # push {r1,r4-r7,lr}; mov r7,r8
}

IWRAM_ROM_BASE = 0x1C7A00
IWRAM_BASE = 0x03005C00
