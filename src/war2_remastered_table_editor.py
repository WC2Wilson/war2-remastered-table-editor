from __future__ import annotations

import ctypes
import json
import os
import re
import struct
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import pymem
    import pymem.exception
    import pymem.process
except Exception:
    pymem = None  # type: ignore[assignment]



APP_TITLE = "Warcraft II Remastered Runtime Table Editor"
APP_VERSION = "1.2.0"
DEFAULT_PROCESS_CANDIDATES = (
    "Warcraft II.exe",
    "Warcraft II Remastered.exe",
)
PAGE_EXECUTE_READWRITE = 0x40
EXPECTED_MACHINE = 0x014C
EXPECTED_TIMESTAMP = 0x699E13E7
EXPECTED_IMAGE_SIZE = 0x0062B000
SUPPORTED_BUILD = "Warcraft II Remastered 1.0.2.2818 x86"

BG = "#121417"
PANEL = "#1b1f24"
PANEL_2 = "#232931"
TEXT = "#e8edf2"
MUTED = "#9aa7b2"
ACCENT = "#44a4ff"
GOOD = "#55d187"
WARN = "#ffc857"
BAD = "#ff6b6b"
BORDER = "#303944"


@dataclass(frozen=True)
class TableDefinition:
    key: str
    title: str
    category: str
    rva: int
    row_names: Tuple[str, ...]
    value_kind: str
    description: str
    element_width: int = 1

    @property
    def size(self) -> int:
        """Number of editable entries in the table."""
        return len(self.row_names)

    @property
    def byte_size(self) -> int:
        return self.size * self.element_width

    @property
    def max_value(self) -> int:
        return (1 << (8 * self.element_width)) - 1

    def decode(self, data: bytes) -> List[int]:
        if len(data) != self.byte_size:
            raise ValueError(
                f"{self.title} expected {self.byte_size} bytes, received {len(data)}."
            )
        if self.element_width == 1:
            return list(data)
        if self.element_width == 2:
            return list(struct.unpack(f"<{self.size}H", data))
        raise ValueError(f"Unsupported element width: {self.element_width}")

    def encode(self, values: Sequence[int]) -> bytes:
        if len(values) != self.size:
            raise ValueError(
                f"{self.title} expected {self.size} values, received {len(values)}."
            )
        for value in values:
            if not isinstance(value, int) or not 0 <= value <= self.max_value:
                raise ValueError(
                    f"Value {value!r} is outside 0–{self.max_value} for {self.title}."
                )
        if self.element_width == 1:
            return bytes(values)
        if self.element_width == 2:
            return struct.pack(f"<{self.size}H", *values)
        raise ValueError(f"Unsupported element width: {self.element_width}")

    def encode_value(self, value: int) -> bytes:
        if not 0 <= value <= self.max_value:
            raise ValueError(f"Value must be between 0 and {self.max_value}.")
        return value.to_bytes(self.element_width, byteorder="little", signed=False)

    def decode_value(self, data: bytes) -> int:
        if len(data) != self.element_width:
            raise ValueError(
                f"Expected {self.element_width} bytes for one value, received {len(data)}."
            )
        return int.from_bytes(data, byteorder="little", signed=False)


BULLET_ROWS = (
    "Lightning",
    "Hammer",
    "Fireball",
    "Fire Shield",
    "Fire Spin",
    "Blizzard",
    "Rot",
    "Human Battle",
    "Exorcism",
    "Heal",
    "Death Knight Attack",
    "Rune",
    "Typhoon",
    "Stone",
    "Bolt",
    "Arrow",
    "Axe",
    "Human Torpedo",
    "Orc Torpedo",
    "Light Fire",
    "Heavy Fire",
    "Catapult Hit",
    "Sparkle",
    "Boom Fire",
    "Cannon Ball",
    "Cannon Fire",
    "Cannon Boom",
    "Demon Fire",
    "Black X",
    "None",
)

ACTION_ROWS = (
    "ORDER_DEAD",
    "ORDER_DIE",
    "ORDER_GUARD",
    "ORDER_MOVE",
    "ORDER_PATROL_MOVE",
    "ORDER_PATROL",
    "ORDER_FOLLOW",
    "ORDER_FOLLOW_GUARD",
    "ORDER_ATTACK",
    "ORDER_ATTACK_TARGET",
    "ORDER_ATTACK_AREA",
    "ORDER_ATTACK_WALL",
    "ORDER_DEFEND",
    "ORDER_STAND",
    "ORDER_STAND_ATTACK",
    "ORDER_DEFEND_GROUND",
    "ORDER_DEFEND_STOPPED",
    "ORDER_ATTACK_GROUND",
    "ORDER_ATTACK_GROUND_MOVE",
    "ORDER_DEMOLISH",
    "ORDER_DEMOLISH_NEAR",
    "ORDER_DEMOLISH_AT",
    "ORDER_PEON_BUILD",
    "ORDER_HARVEST",
    "ORDER_RETURN",
    "ORDER_ENTER",
    "ORDER_LEAVE",
    "ORDER_REPAIR",
    "ORDER_CREATE_BLDG",
    "ORDER_UNLOAD_ALL",
    "ORDER_DOCK",
    "ORDER_UNDOCK",
    "ORDER_WAIT",
    "ORDER_BLDG_WAIT",
    "ORDER_ENTER_TRANSPORT",
    "ORDER_LEAVE_TRANSPORT",
    "ORDER_TRAVELING",
    "ORDER_BLDG_BUILD",
    "SPELL_VISION",
    "SPELL_HEAL",
    "SPELL_AREAHEAL",
    "SPELL_EXORCISM",
    "SPELL_FIRESHIELD",
    "SPELL_FIREBALL",
    "SPELL_SLOW",
    "SPELL_INVIS",
    "SPELL_POLYMORPH",
    "SPELL_BLIZZARD",
    "SPELL_EYE",
    "SPELL_BLOODLUST",
    "SPELL_RAISEDEAD",
    "SPELL_DRAINLIFE",
    "SPELL_WHIRLWIND",
    "SPELL_HASTE",
    "SPELL_ARMOR",
    "SPELL_RUNES",
    "SPELL_ROT",
    "ORDER_RESURRECT",
    "ORDER_WAIT_CONVERT",
    "ORDER_VICTORY_CIRCLE",
    "ORDER_NONE",
)

UPGRADE_ROWS = (
    "Arrows",
    "Swords",
    "Shields",
    "Boat Attack",
    "Boat Armor",
    "Boat Speed",
    "Catapult Damage",
    "Ranger Upgrade",
    "Longbow Upgrade",
    "Scouts Upgrade",
    "Marksmanship Upgrade",
)

BULLET_ACTION_ROWS = (
    "B_ORDER_INIT",
    "B_ORDER_MOVE_LOOP",
    "B_ORDER_MOVE_LINEAR",
    "B_ORDER_WIND",
    "B_ORDER_RAIN",
    "B_ORDER_STAY",
    "B_ORDER_FINISH",
    "B_ORDER_FIREBALL",
    "B_ORDER_FIRESHIELD",
    "B_ORDER_FIRESPIN",
    "B_ORDER_BLIZZARD",
    "B_ORDER_ROT",
    "B_ORDER_TYPHOON",
    "B_ORDER_BLACK_X",
    "B_ORDER_NONE",
)

CASTING_COST_NOTES: Mapping[str, str] = {
    "SPELL_VISION": "per area viewed",
    "SPELL_HEAL": "per point healed",
    "SPELL_AREAHEAL": "per point healed",
    "SPELL_EXORCISM": "per damage dealt to undead",
    "SPELL_FIRESHIELD": "per unit enchanted",
    "SPELL_FIREBALL": "per fireball cast",
    "SPELL_SLOW": "per unit slowed",
    "SPELL_INVIS": "per unit enchanted",
    "SPELL_POLYMORPH": "per unit polymorphed",
    "SPELL_BLIZZARD": "per shard set created",
    "SPELL_EYE": "per eye created",
    "SPELL_BLOODLUST": "per unit enchanted",
    "SPELL_RAISEDEAD": "per skeleton raised",
    "SPELL_DRAINLIFE": "per unit enchanted",
    "SPELL_WHIRLWIND": "per whirlwind created",
    "SPELL_HASTE": "per unit hasted",
    "SPELL_ARMOR": "per unit armored",
    "SPELL_RUNES": "per exploding rune",
    "SPELL_ROT": "per rot set created",
}

TABLES: Tuple[TableDefinition, ...] = (
    TableDefinition(
        "upgrade_steps",
        "Upgrade Steps",
        "Upgrades",
        0x4C11DD,
        UPGRADE_ROWS,
        "byte",
        "Amount added per upgrade level. Scouts may use 255 as a calculated/special value.",
    ),
    TableDefinition(
        "bullet_min_range",
        "Projectile Minimum Range",
        "Projectiles",
        0x4C08EC,
        BULLET_ROWS,
        "byte",
        "Minimum projectile range in matrices/tiles.",
    ),
    TableDefinition(
        "bullet_area_effect",
        "Projectile Area Effect",
        "Projectiles",
        0x4C090B,
        BULLET_ROWS,
        "bool",
        "Whether the projectile uses area-effect behavior.",
    ),
    TableDefinition(
        "bullet_orders",
        "Projectile Orders",
        "Projectiles",
        0x4C0ACC,
        BULLET_ROWS,
        "bullet_order",
        "Projectile animation/movement order, values 0 through 15.",
    ),
    TableDefinition(
        "bullet_action_sequence",
        "Bullet Action to Sequence",
        "Projectiles",
        0x4C5E68,
        BULLET_ACTION_ROWS,
        "bullet_sequence",
        "Maps each bullet action order to BSEQ_INIT, BSEQ_MOVE, or BSEQ_FINISH.",
    ),
    TableDefinition(
        "bullet_speed",
        "Projectile Speed",
        "Projectiles",
        0x4C0AEC,
        BULLET_ROWS,
        "byte",
        "Projectile movement speed. Zero is used by stationary visual effects.",
    ),
    TableDefinition(
        "bullet_pierce",
        "Projectile Pierce Damage",
        "Projectiles",
        0x4C0B0C,
        BULLET_ROWS,
        "pierce",
        "Piercing behavior: commonly 0=False, 1=True, and 255=not applicable/special.",
    ),
    TableDefinition(
        "action_sequence",
        "Action to Unit Sequence",
        "Orders and Spells",
        0x4C1360,
        ACTION_ROWS,
        "unit_sequence",
        "Maps each order/spell to the unit animation sequence it plays.",
    ),
    TableDefinition(
        "action_flags",
        "Action Flags",
        "Orders and Spells",
        0x4C1684,
        ACTION_ROWS,
        "action_flags",
        "Bit flags: 0x01 unmask always, 0x02 unmask when the action has a target.",
    ),
    TableDefinition(
        "ranged_order",
        "Order / Spell Range",
        "Orders and Spells",
        0x4C1744,
        ACTION_ROWS,
        "range",
        "Range byte used by orders and spells. 255 is NO_RANGE; spell ranges use raw tile values.",
    ),
    TableDefinition(
        "casting_cost",
        "Casting Cost",
        "Orders and Spells",
        0x4C5EDE,
        ACTION_ROWS,
        "casting_cost",
        "Mana/casting cost table stored as 61 little-endian unsigned 16-bit values (UWORD).",
        element_width=2,
    ),
    TableDefinition(
        "spell_area_effect",
        "Spell Area Effect",
        "Orders and Spells",
        0x4C1804,
        ACTION_ROWS,
        "bool",
        "Whether the corresponding spell/order is treated as an area effect.",
    ),
    TableDefinition(
        "can_follow",
        "Can Follow",
        "Orders and Spells",
        0x4C1844,
        ACTION_ROWS,
        "bool",
        "Whether units performing the order can participate in follow behavior.",
    ),
    TableDefinition(
        "path_adjust_target",
        "Path Adjust Target",
        "Orders and Spells",
        0x4C18C4,
        ACTION_ROWS,
        "bool",
        "Whether pathfinding adjusts the target for the order/spell.",
    ),
    TableDefinition(
        "attack_order",
        "Attack Order",
        "Orders and Spells",
        0x5181BC,
        ACTION_ROWS,
        "bool",
        "Whether the order is classified as an attack order.",
    ),
)

TABLE_BY_KEY: Dict[str, TableDefinition] = {table.key: table for table in TABLES}

BULLET_ORDER_NAMES: Mapping[int, str] = {
    0: "B_ORDER_INIT",
    1: "B_ORDER_MOVE_LOOP",
    2: "B_ORDER_MOVE_LINEAR",
    3: "B_ORDER_WIND",
    4: "B_ORDER_RAIN",
    5: "B_ORDER_STAY",
    6: "B_ORDER_FINISH",
    7: "B_ORDER_FIREBALL",
    8: "B_ORDER_FIRESHIELD",
    9: "B_ORDER_FIRESPIN",
    10: "B_ORDER_BLIZZARD",
    11: "B_ORDER_ROT",
    12: "B_ORDER_TYPHOON",
    13: "B_ORDER_BLACK_X",
    14: "B_ORDER_NONE",
    15: "NUM_BULLET_ACTIONS",
}

BULLET_SEQUENCE_NAMES: Mapping[int, str] = {
    0: "BSEQ_INIT",
    1: "BSEQ_MOVE",
    2: "BSEQ_FINISH",
}

UNIT_SEQUENCE_NAMES: Mapping[int, str] = {
    0: "USEQ_DEAD",
    1: "USEQ_DIE",
    2: "USEQ_STOP",
    3: "USEQ_MOVE",
    4: "USEQ_ATTACK",
    5: "USEQ_BUILD",
    6: "USEQ_ENTER_SHORE",
}

ACTION_FLAG_NAMES: Mapping[int, str] = {
    0: "None",
    1: "AF_UNMASK_ALWAYS",
    2: "AF_UNMASK_TARGET",
    3: "ALWAYS | TARGET",
}

RANGE_NAMES: Mapping[int, str] = {
    255: "NO_RANGE",
    12: "Range 12 (Blizzard/Rot/Whirlwind)",
    10: "Range 10 (long spell range)",
    6: "Range 6 (short spell range)",
}


class BackendError(RuntimeError):
    pass


class MemoryBackend:
    display_name = "Disconnected"

    def read(self, rva: int, size: int) -> bytes:
        raise NotImplementedError

    def write(self, rva: int, data: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class LiveProcessBackend(MemoryBackend):
    def __init__(self, process_name: str, module_name: Optional[str] = None):
        if os.name != "nt":
            raise BackendError("Live process editing requires Windows.")
        if pymem is None:
            raise BackendError("The pymem package is not installed.")

        self.process_name = process_name.strip()
        self.pm = pymem.Pymem(self.process_name)
        requested_module = (module_name or self.process_name).strip()
        module = pymem.process.module_from_name(self.pm.process_handle, requested_module)
        if module is None:
            # Some process names and module names differ only by path/casing.
            modules = list(self.pm.list_modules())
            module = next(
                (
                    item
                    for item in modules
                    if Path(item.name).name.lower() == Path(requested_module).name.lower()
                ),
                None,
            )
        if module is None:
            self.pm.close_process()
            raise BackendError(f"Module '{requested_module}' was not found in '{self.process_name}'.")

        self.module_name = module.name
        self.base = int(module.lpBaseOfDll)
        self.module_size = int(module.SizeOfImage)
        self._validate_supported_build()
        self.display_name = (
            f"Live: {self.process_name} | {self.module_name} | "
            f"base 0x{self.base:08X} | size 0x{self.module_size:X}"
        )

    def _validate_supported_build(self) -> None:
        if self.module_size != EXPECTED_IMAGE_SIZE:
            self.pm.close_process()
            raise BackendError(
                f"Unsupported Warcraft II build: image size 0x{self.module_size:X}; "
                f"expected 0x{EXPECTED_IMAGE_SIZE:X} for {SUPPORTED_BUILD}."
            )
        try:
            dos = bytes(self.pm.read_bytes(self.base, 0x1000))
            if dos[:2] != b"MZ":
                raise ValueError("missing MZ header")
            pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
            if pe_offset + 0x54 > len(dos):
                dos = bytes(self.pm.read_bytes(self.base, pe_offset + 0x100))
            if dos[pe_offset:pe_offset + 4] != b"PE\0\0":
                raise ValueError("missing PE header")
            machine = struct.unpack_from("<H", dos, pe_offset + 4)[0]
            timestamp = struct.unpack_from("<I", dos, pe_offset + 8)[0]
            image_size = struct.unpack_from("<I", dos, pe_offset + 0x50)[0]
        except Exception as exc:
            self.pm.close_process()
            raise BackendError(f"Could not validate the running Warcraft II module: {exc}") from exc
        if machine != EXPECTED_MACHINE or timestamp != EXPECTED_TIMESTAMP or image_size != EXPECTED_IMAGE_SIZE:
            self.pm.close_process()
            raise BackendError(
                "Unsupported Warcraft II executable fingerprint: "
                f"machine=0x{machine:04X}, timestamp=0x{timestamp:08X}, image=0x{image_size:X}. "
                f"Expected {SUPPORTED_BUILD}."
            )

    def _absolute(self, rva: int, size: int) -> int:
        if rva < 0 or size < 0:
            raise BackendError("Negative RVA or size is invalid.")
        if rva + size > self.module_size:
            raise BackendError(
                f"RVA 0x{rva:X} + {size} bytes exceeds module size 0x{self.module_size:X}."
            )
        return self.base + rva

    def read(self, rva: int, size: int) -> bytes:
        address = self._absolute(rva, size)
        try:
            return bytes(self.pm.read_bytes(address, size))
        except Exception as exc:
            raise BackendError(f"Read failed at 0x{address:08X}: {exc}") from exc

    def write(self, rva: int, data: bytes) -> None:
        address = self._absolute(rva, len(data))
        old_protect = ctypes.c_ulong()
        kernel32 = ctypes.windll.kernel32
        changed = kernel32.VirtualProtectEx(
            self.pm.process_handle,
            ctypes.c_void_p(address),
            ctypes.c_size_t(len(data)),
            PAGE_EXECUTE_READWRITE,
            ctypes.byref(old_protect),
        )
        if not changed:
            raise BackendError(
                f"VirtualProtectEx failed at 0x{address:08X} (WinError {ctypes.get_last_error()})."
            )
        try:
            self.pm.write_bytes(address, data, len(data))
        except Exception as exc:
            raise BackendError(f"Write failed at 0x{address:08X}: {exc}") from exc
        finally:
            restored = ctypes.c_ulong()
            kernel32.VirtualProtectEx(
                self.pm.process_handle,
                ctypes.c_void_p(address),
                ctypes.c_size_t(len(data)),
                old_protect.value,
                ctypes.byref(restored),
            )
            kernel32.FlushInstructionCache(
                self.pm.process_handle,
                ctypes.c_void_p(address),
                ctypes.c_size_t(len(data)),
            )

    def close(self) -> None:
        try:
            self.pm.close_process()
        except Exception:
            pass


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(
            self,
            bg=PANEL,
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.window_id, width=event.width),
        )


class War2TableEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("1320x820")
        self.minsize(1050, 680)
        self.configure(bg=BG)

        self.backend: Optional[MemoryBackend] = None
        self.current_table: TableDefinition = TABLES[0]
        self.live_values: Dict[str, List[int]] = {}
        self.original_values: Dict[str, List[int]] = {}
        self.pending_values: Dict[str, Dict[int, int]] = {table.key: {} for table in TABLES}
        self.table_buttons: Dict[str, ttk.Button] = {}
        self._filter_job: Optional[str] = None

        self.process_var = tk.StringVar(value=DEFAULT_PROCESS_CANDIDATES[0])
        self.module_var = tk.StringVar(value=DEFAULT_PROCESS_CANDIDATES[0])
        self.status_var = tk.StringVar(value="Runtime-only: attach to Warcraft II.exe")
        self.table_title_var = tk.StringVar()
        self.table_info_var = tk.StringVar()
        self.selected_row_var = tk.StringVar(value="No row selected")
        self.value_var = tk.StringVar()
        self.value_hint_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.immediate_var = tk.BooleanVar(value=False)

        self._configure_styles()
        self._build_ui()
        self._bind_events()
        self._select_table(TABLES[0].key)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL_2)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel2.TFrame", background=PANEL_2)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 16, "bold"))
        style.configure("TableTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", background=PANEL_2, foreground=MUTED)
        style.configure(
            "TButton",
            background=PANEL_2,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
            padding=(10, 7),
        )
        style.map(
            "TButton",
            background=[("active", "#303844"), ("pressed", "#1a2027")],
            foreground=[("disabled", "#66717c")],
        )
        style.configure("Accent.TButton", background="#176bb0", foreground="white")
        style.map("Accent.TButton", background=[("active", "#2184d4"), ("pressed", "#12558c")])
        style.configure("Danger.TButton", background="#7a3030", foreground="white")
        style.map("Danger.TButton", background=[("active", "#a03b3b"), ("pressed", "#5f2424")])
        style.configure("Sidebar.TButton", anchor="w", padding=(12, 8))
        style.configure("Selected.Sidebar.TButton", anchor="w", padding=(12, 8), background="#1f5f91")
        style.map("Selected.Sidebar.TButton", background=[("active", "#287bb9")])
        style.configure("TEntry", fieldbackground=PANEL_2, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.configure("TCombobox", fieldbackground=PANEL_2, foreground=TEXT, arrowcolor=TEXT)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PANEL_2)],
            selectbackground=[("readonly", PANEL_2)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=27,
            bordercolor=BORDER,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_2,
            foreground=TEXT,
            relief="flat",
            padding=(8, 6),
        )
        style.map("Treeview", background=[("selected", "#245d87")], foreground=[("selected", "white")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, style="Panel2.TFrame", padding=(14, 10))
        top.pack(fill="x")

        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").pack(side="left")

        connection = ttk.Frame(top, style="Panel2.TFrame")
        connection.pack(side="right")
        ttk.Label(connection, text="Process:", style="Status.TLabel").grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(connection, width=22, textvariable=self.process_var).grid(row=0, column=1, padx=(0, 7))
        ttk.Label(connection, text="Module:", style="Status.TLabel").grid(row=0, column=2, padx=(0, 5))
        ttk.Entry(connection, width=22, textvariable=self.module_var).grid(row=0, column=3, padx=(0, 7))
        ttk.Button(connection, text="Auto Attach", style="Accent.TButton", command=self._auto_attach).grid(row=0, column=4, padx=3)
        ttk.Button(connection, text="Attach", command=self._attach_process).grid(row=0, column=5, padx=3)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        sidebar = ttk.Frame(body, style="Panel.TFrame", width=250)
        main = ttk.Frame(body, style="Panel.TFrame")
        body.add(sidebar, weight=0)
        body.add(main, weight=1)

        ttk.Label(sidebar, text="TABLES", style="Muted.TLabel", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=12, pady=(12, 7)
        )

        side_scroll = ScrollableFrame(sidebar)
        side_scroll.pack(fill="both", expand=True)
        current_category = None
        for table in TABLES:
            if table.category != current_category:
                current_category = table.category
                ttk.Label(
                    side_scroll.inner,
                    text=current_category.upper(),
                    style="Muted.TLabel",
                    font=("Segoe UI", 8, "bold"),
                ).pack(fill="x", padx=10, pady=(12, 4))
            button = ttk.Button(
                side_scroll.inner,
                text=table.title,
                style="Sidebar.TButton",
                command=lambda key=table.key: self._select_table(key),
            )
            button.pack(fill="x", padx=8, pady=2)
            self.table_buttons[table.key] = button

        side_actions = ttk.Frame(sidebar, style="Panel.TFrame", padding=8)
        side_actions.pack(fill="x")
        ttk.Button(side_actions, text="Export Preset", command=self._export_preset).pack(fill="x", pady=2)
        ttk.Button(side_actions, text="Import Preset", command=self._import_preset).pack(fill="x", pady=2)
        ttk.Button(side_actions, text="Save Snapshot", command=self._save_snapshot).pack(fill="x", pady=2)

        header = ttk.Frame(main, style="Panel.TFrame", padding=(14, 12))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.table_title_var, style="TableTitle.TLabel").pack(anchor="w")
        ttk.Label(header, textvariable=self.table_info_var, style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(4, 0))

        toolbar = ttk.Frame(main, style="Panel.TFrame", padding=(12, 0, 12, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Refresh Table", command=self._refresh_current_table).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Apply Table", style="Accent.TButton", command=self._apply_current_table).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Apply All Pending", style="Accent.TButton", command=self._apply_all_pending).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Restore Table Snapshot", command=self._restore_current_table).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Restore All Snapshots", style="Danger.TButton", command=self._restore_all_tables).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Copy Bytes", command=self._copy_current_bytes).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Paste Bytes", command=self._paste_table_bytes).pack(side="left", padx=3)

        search_frame = ttk.Frame(toolbar, style="Panel.TFrame")
        search_frame.pack(side="right")
        ttk.Label(search_frame, text="Filter:", style="Panel.TLabel").pack(side="left", padx=(0, 5))
        ttk.Entry(search_frame, width=24, textvariable=self.filter_var).pack(side="left")

        table_frame = ttk.Frame(main, style="Panel.TFrame", padding=(12, 0))
        table_frame.pack(fill="both", expand=True)

        columns = ("index", "name", "current", "pending", "hex", "meaning")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("index", text="#")
        self.tree.heading("name", text="Entry")
        self.tree.heading("current", text="Current")
        self.tree.heading("pending", text="Pending")
        self.tree.heading("hex", text="Hex")
        self.tree.heading("meaning", text="Meaning")
        self.tree.column("index", width=55, anchor="center", stretch=False)
        self.tree.column("name", width=245, anchor="w")
        self.tree.column("current", width=90, anchor="center", stretch=False)
        self.tree.column("pending", width=90, anchor="center", stretch=False)
        self.tree.column("hex", width=85, anchor="center", stretch=False)
        self.tree.column("meaning", width=310, anchor="w")
        self.tree.tag_configure("changed", background="#2d3321")
        self.tree.tag_configure("unread", foreground=MUTED)
        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        edit = ttk.Frame(main, style="Panel2.TFrame", padding=(12, 10))
        edit.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Label(edit, textvariable=self.selected_row_var, style="Status.TLabel", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 7)
        )
        ttk.Label(edit, text="Value:", style="Status.TLabel").grid(row=1, column=0, sticky="w")
        self.value_combo = ttk.Combobox(edit, width=36, textvariable=self.value_var)
        self.value_combo.grid(row=1, column=1, sticky="ew", padx=(6, 8))
        ttk.Button(edit, text="Stage Row", command=self._stage_selected_row).grid(row=1, column=2, padx=3)
        ttk.Button(edit, text="Write Row Now", style="Accent.TButton", command=self._write_selected_row).grid(row=1, column=3, padx=3)
        ttk.Button(edit, text="Undo Pending", command=self._undo_selected_pending).grid(row=1, column=4, padx=3)
        ttk.Checkbutton(
            edit,
            text="Write immediately when Enter is pressed",
            variable=self.immediate_var,
        ).grid(row=2, column=1, sticky="w", pady=(7, 0))
        ttk.Label(edit, textvariable=self.value_hint_var, style="Status.TLabel").grid(
            row=2, column=2, columnspan=3, sticky="w", padx=(6, 0), pady=(7, 0)
        )
        edit.columnconfigure(1, weight=1)

        status = ttk.Frame(self, style="Panel2.TFrame", padding=(10, 6))
        status.pack(fill="x")
        self.status_label = ttk.Label(status, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(side="left")
        ttk.Label(status, text=f"v{APP_VERSION}", style="Status.TLabel").pack(side="right")

    def _bind_events(self) -> None:
        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self.tree.bind("<Double-1>", lambda _event: self.value_combo.focus_set())
        self.value_combo.bind("<Return>", self._on_value_enter)
        self.filter_var.trace_add("write", self._on_filter_changed)
        self.bind("<F5>", lambda _event: self._refresh_current_table())
        self.bind("<Control-s>", lambda _event: self._apply_current_table())
        self.bind("<Control-e>", lambda _event: self._export_preset())
        self.bind("<Control-o>", lambda _event: self._import_preset())

    def _set_status(self, text: str, level: str = "normal") -> None:
        self.status_var.set(text)
        colors = {"normal": MUTED, "good": GOOD, "warn": WARN, "bad": BAD}
        self.status_label.configure(foreground=colors.get(level, MUTED))
        self.update_idletasks()

    def _set_backend(self, backend: MemoryBackend) -> None:
        if self.backend is not None:
            self.backend.close()
        self.backend = backend
        self.live_values.clear()
        self.original_values.clear()
        self.pending_values = {table.key: {} for table in TABLES}
        self._read_all_tables(capture_snapshot=True)
        self._select_table(self.current_table.key)
        self._set_status(f"Connected — {backend.display_name}", "good")

    def _auto_attach(self) -> None:
        errors: List[str] = []
        candidates = []
        user_process = self.process_var.get().strip()
        if user_process:
            candidates.append(user_process)
        candidates.extend(name for name in DEFAULT_PROCESS_CANDIDATES if name not in candidates)

        for process_name in candidates:
            module_candidates = [self.module_var.get().strip(), process_name]
            for module_name in dict.fromkeys(name for name in module_candidates if name):
                try:
                    backend = LiveProcessBackend(process_name, module_name)
                    self.process_var.set(process_name)
                    self.module_var.set(module_name)
                    self._set_backend(backend)
                    return
                except Exception as exc:
                    errors.append(f"{process_name} / {module_name}: {exc}")
        messagebox.showerror(
            "Auto Attach Failed",
            "Could not attach to a supported Warcraft II process.\n\n" + "\n".join(errors[-4:]),
        )
        self._set_status("Auto attach failed", "bad")

    def _attach_process(self) -> None:
        try:
            backend = LiveProcessBackend(self.process_var.get(), self.module_var.get())
            self._set_backend(backend)
        except Exception as exc:
            self._show_error("Attach Failed", exc)

    def _read_all_tables(self, capture_snapshot: bool = False) -> None:
        if self.backend is None:
            raise BackendError("No live Warcraft II process is attached.")
        failures = []
        for table in TABLES:
            try:
                values = table.decode(self.backend.read(table.rva, table.byte_size))
                self.live_values[table.key] = values
                if capture_snapshot or table.key not in self.original_values:
                    self.original_values[table.key] = values.copy()
            except Exception as exc:
                failures.append(f"{table.title}: {exc}")
        if failures:
            raise BackendError("Some tables could not be read:\n" + "\n".join(failures))

    def _read_table(self, table: TableDefinition, preserve_pending: bool = True) -> List[int]:
        if self.backend is None:
            raise BackendError("No live Warcraft II process is attached.")
        values = table.decode(self.backend.read(table.rva, table.byte_size))
        self.live_values[table.key] = values
        if not preserve_pending:
            self.pending_values[table.key].clear()
        return values

    def _select_table(self, key: str) -> None:
        self.current_table = TABLE_BY_KEY[key]
        for table_key, button in self.table_buttons.items():
            button.configure(style="Selected.Sidebar.TButton" if table_key == key else "Sidebar.TButton")
        table = self.current_table
        storage = "byte" if table.element_width == 1 else "little-endian UWORD"
        self.table_title_var.set(
            f"{table.title}  —  RVA 0x{table.rva:08X}  —  "
            f"{table.size} entries / {table.byte_size} bytes  —  {storage}"
        )
        self.table_info_var.set(table.description)
        self.selected_row_var.set("No row selected")
        self.value_var.set("")
        self.value_hint_var.set(self._kind_hint(table.value_kind))
        self._configure_value_combo(table.value_kind)
        self._populate_tree()

    def _configure_value_combo(self, kind: str) -> None:
        choices: Sequence[str]
        state = "normal"
        if kind == "bool":
            choices = ("0 - False", "1 - True")
        elif kind == "bullet_order":
            choices = tuple(f"{key} - {value}" for key, value in BULLET_ORDER_NAMES.items())
        elif kind == "unit_sequence":
            choices = tuple(f"{key} - {value}" for key, value in UNIT_SEQUENCE_NAMES.items())
        elif kind == "bullet_sequence":
            choices = tuple(f"{key} - {value}" for key, value in BULLET_SEQUENCE_NAMES.items())
        elif kind == "action_flags":
            choices = tuple(f"{key} - {value}" for key, value in ACTION_FLAG_NAMES.items())
        elif kind == "pierce":
            choices = ("0 - False", "1 - True", "255 - Special / N/A")
        elif kind == "range":
            choices = tuple(f"{key} - {value}" for key, value in RANGE_NAMES.items())
        else:
            choices = ()
        self.value_combo.configure(values=choices, state=state)

    @staticmethod
    def _kind_hint(kind: str) -> str:
        hints = {
            "bool": "Allowed: 0 or 1",
            "bullet_order": "Allowed: 0–15",
            "unit_sequence": "Allowed: 0–6",
            "bullet_sequence": "Allowed: 0–2 (BSEQ_INIT, BSEQ_MOVE, BSEQ_FINISH)",
            "casting_cost": "Allowed: 0–65,535; stored as a little-endian UWORD",
            "action_flags": "Allowed: 0–255; known bits are 0x01 and 0x02",
            "pierce": "Typical: 0, 1, or 255",
            "range": "Allowed: 0–255; 255 means NO_RANGE",
            "byte": "Allowed: 0–255; decimal or 0x-prefixed hex",
        }
        return hints.get(kind, "Allowed: 0–255")

    def _meaning(self, kind: str, value: int, row_name: Optional[str] = None) -> str:
        if kind == "bool":
            return "True" if value else "False" if value == 0 else "Non-standard boolean"
        if kind == "bullet_order":
            return BULLET_ORDER_NAMES.get(value, "Unknown projectile order")
        if kind == "unit_sequence":
            return UNIT_SEQUENCE_NAMES.get(value, "Unknown sequence")
        if kind == "bullet_sequence":
            return BULLET_SEQUENCE_NAMES.get(value, "Unknown bullet sequence")
        if kind == "casting_cost":
            note = CASTING_COST_NOTES.get(row_name or "")
            if note:
                return f"Cost {value} — {note}"
            return "No casting cost" if value == 0 else f"Casting cost {value}"
        if kind == "action_flags":
            if value in ACTION_FLAG_NAMES:
                return ACTION_FLAG_NAMES[value]
            parts = []
            if value & 0x01:
                parts.append("UNMASK_ALWAYS")
            if value & 0x02:
                parts.append("UNMASK_TARGET")
            unknown = value & ~0x03
            if unknown:
                parts.append(f"unknown bits 0x{unknown:02X}")
            return " | ".join(parts) if parts else "None"
        if kind == "pierce":
            return {0: "False", 1: "True", 255: "Special / N/A"}.get(value, "Custom")
        if kind == "range":
            return RANGE_NAMES.get(value, f"Raw range {value}")
        return "Raw byte"

    def _effective_value(self, table: TableDefinition, index: int) -> Optional[int]:
        if index in self.pending_values[table.key]:
            return self.pending_values[table.key][index]
        values = self.live_values.get(table.key)
        if values is None or index >= len(values):
            return None
        return values[index]

    def _populate_tree(self) -> None:
        selected_index = self._selected_index()
        self.tree.delete(*self.tree.get_children())
        table = self.current_table
        filter_text = self.filter_var.get().strip().lower()
        live = self.live_values.get(table.key)
        pending = self.pending_values[table.key]

        for index, name in enumerate(table.row_names):
            if filter_text and filter_text not in name.lower() and filter_text not in str(index):
                continue
            current = live[index] if live is not None and index < len(live) else None
            staged = pending.get(index)
            effective = staged if staged is not None else current
            current_text = "—" if current is None else str(current)
            pending_text = "" if staged is None else str(staged)
            hex_width = table.element_width * 2
            hex_text = "—" if effective is None else f"0x{effective:0{hex_width}X}"
            meaning = "Not connected" if effective is None else self._meaning(table.value_kind, effective, name)
            tags = ("changed",) if staged is not None else (("unread",) if current is None else ())
            item = self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(index, name, current_text, pending_text, hex_text, meaning),
                tags=tags,
            )
            if selected_index == index:
                self.tree.selection_set(item)
                self.tree.focus(item)
        self._update_pending_badges()

    def _update_pending_badges(self) -> None:
        for table in TABLES:
            count = len(self.pending_values[table.key])
            label = table.title if count == 0 else f"{table.title}  ({count})"
            self.table_buttons[table.key].configure(text=label)

    def _selected_index(self) -> Optional[int]:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (TypeError, ValueError):
            return None

    def _on_row_selected(self, _event=None) -> None:
        index = self._selected_index()
        if index is None:
            return
        table = self.current_table
        value = self._effective_value(table, index)
        self.selected_row_var.set(f"Row {index}: {table.row_names[index]}")
        self.value_var.set("" if value is None else str(value))
        if value is None:
            self.value_hint_var.set(self._kind_hint(table.value_kind))
        else:
            self.value_hint_var.set(f"{self._kind_hint(table.value_kind)} — {self._meaning(table.value_kind, value, table.row_names[index])}")

    def _on_filter_changed(self, *_args) -> None:
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(120, self._populate_tree)

    def _on_value_enter(self, _event=None) -> str:
        if self.immediate_var.get():
            self._write_selected_row()
        else:
            self._stage_selected_row()
        return "break"

    @staticmethod
    def _parse_value(text: str, max_value: int) -> int:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Enter a value.")
        # Combobox entries are formatted as "number - description".
        cleaned = cleaned.split("-", 1)[0].strip()
        if cleaned.lower().startswith("0x"):
            value = int(cleaned, 16)
        else:
            value = int(cleaned, 10)
        if not 0 <= value <= max_value:
            raise ValueError(f"Value must be between 0 and {max_value}.")
        return value

    @staticmethod
    def _validate_kind(kind: str, value: int) -> None:
        if kind == "bool" and value not in (0, 1):
            raise ValueError("This table only accepts 0 or 1.")
        if kind == "bullet_order" and not 0 <= value <= 15:
            raise ValueError("Projectile orders must be between 0 and 15.")
        if kind == "unit_sequence" and not 0 <= value <= 6:
            raise ValueError("Unit sequences must be between 0 and 6.")
        if kind == "bullet_sequence" and not 0 <= value <= 2:
            raise ValueError("Bullet sequences must be between 0 and 2.")

    def _stage_selected_row(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showwarning("No Row Selected", "Select a table row first.")
            return
        try:
            value = self._parse_value(self.value_var.get(), self.current_table.max_value)
            self._validate_kind(self.current_table.value_kind, value)
            live = self.live_values.get(self.current_table.key)
            if live is not None and live[index] == value:
                self.pending_values[self.current_table.key].pop(index, None)
            else:
                self.pending_values[self.current_table.key][index] = value
            self._populate_tree()
            if self.tree.exists(str(index)):
                self.tree.selection_set(str(index))
                self.tree.focus(str(index))
            self._set_status(
                f"Staged {self.current_table.title}[{index}] = {value} "
                f"(0x{value:0{self.current_table.element_width * 2}X})",
                "warn",
            )
        except Exception as exc:
            self._show_error("Invalid Value", exc)

    def _write_selected_row(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showwarning("No Row Selected", "Select a table row first.")
            return
        try:
            self._require_backend()
            value = self._parse_value(self.value_var.get(), self.current_table.max_value)
            self._validate_kind(self.current_table.value_kind, value)
            rva = self.current_table.rva + (index * self.current_table.element_width)
            encoded = self.current_table.encode_value(value)
            self.backend.write(rva, encoded)  # type: ignore[union-attr]
            verify = self.current_table.decode_value(
                self.backend.read(rva, self.current_table.element_width)
            )  # type: ignore[union-attr]
            if verify != value:
                raise BackendError(f"Verification failed: wrote {value}, read back {verify}.")
            self.live_values.setdefault(self.current_table.key, [0] * self.current_table.size)[index] = verify
            self.pending_values[self.current_table.key].pop(index, None)
            self._populate_tree()
            if self.tree.exists(str(index)):
                self.tree.selection_set(str(index))
                self.tree.focus(str(index))
            self._set_status(
                f"Wrote {self.current_table.title}[{index}] = {verify} at RVA 0x{rva:08X}",
                "good",
            )
        except Exception as exc:
            self._show_error("Write Failed", exc)

    def _undo_selected_pending(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self.pending_values[self.current_table.key].pop(index, None)
        self._populate_tree()
        if self.tree.exists(str(index)):
            self.tree.selection_set(str(index))
        self._on_row_selected()
        self._set_status("Pending row change removed", "normal")

    def _refresh_current_table(self) -> None:
        try:
            self._require_backend()
            self._read_table(self.current_table, preserve_pending=True)
            self._populate_tree()
            self._set_status(f"Refreshed {self.current_table.title}", "good")
        except Exception as exc:
            self._show_error("Refresh Failed", exc)

    def _apply_table(self, table: TableDefinition) -> int:
        self._require_backend()
        pending = self.pending_values[table.key]
        if not pending:
            return 0
        current = self.live_values.get(table.key)
        if current is None:
            current = self._read_table(table, preserve_pending=True)
        output = current.copy()
        for index, value in pending.items():
            self._validate_kind(table.value_kind, value)
            output[index] = value
        data = table.encode(output)
        self.backend.write(table.rva, data)  # type: ignore[union-attr]
        verify = self.backend.read(table.rva, table.byte_size)  # type: ignore[union-attr]
        if verify != data:
            mismatch = next((i for i, (a, b) in enumerate(zip(data, verify)) if a != b), -1)
            row = mismatch // table.element_width if mismatch >= 0 else -1
            raise BackendError(
                f"Verification failed for {table.title} at row {row} "
                f"(byte offset {mismatch}): expected "
                f"{data[mismatch] if mismatch >= 0 else '?'}, "
                f"read {verify[mismatch] if mismatch >= 0 else '?'}"
            )
        changed = len(pending)
        self.live_values[table.key] = table.decode(verify)
        pending.clear()
        return changed

    def _apply_current_table(self) -> None:
        try:
            changed = self._apply_table(self.current_table)
            self._populate_tree()
            if changed:
                self._set_status(f"Applied and verified {changed} change(s) in {self.current_table.title}", "good")
            else:
                self._set_status("No pending changes in this table", "normal")
        except Exception as exc:
            self._show_error("Apply Table Failed", exc)

    def _apply_all_pending(self) -> None:
        try:
            self._require_backend()
            total = 0
            changed_tables = 0
            for table in TABLES:
                count = self._apply_table(table)
                if count:
                    total += count
                    changed_tables += 1
            self._populate_tree()
            if total:
                self._set_status(f"Applied and verified {total} change(s) across {changed_tables} table(s)", "good")
            else:
                self._set_status("There are no pending changes", "normal")
        except Exception as exc:
            self._show_error("Apply All Failed", exc)

    def _restore_current_table(self) -> None:
        try:
            self._require_backend()
            values = self.original_values.get(self.current_table.key)
            if values is None:
                raise BackendError("No session snapshot exists for this table.")
            data = self.current_table.encode(values)
            self.backend.write(self.current_table.rva, data)  # type: ignore[union-attr]
            verify = self.backend.read(self.current_table.rva, self.current_table.byte_size)  # type: ignore[union-attr]
            if verify != data:
                raise BackendError("Snapshot restore verification failed.")
            self.live_values[self.current_table.key] = self.current_table.decode(verify)
            self.pending_values[self.current_table.key].clear()
            self._populate_tree()
            self._set_status(f"Restored {self.current_table.title} to its attach-time runtime snapshot", "good")
        except Exception as exc:
            self._show_error("Restore Failed", exc)

    def _restore_all_tables(self) -> None:
        try:
            self._require_backend()
            if not self.original_values:
                raise BackendError("No attach-time runtime snapshot is available.")
            for table in TABLES:
                values = self.original_values.get(table.key)
                if values is None:
                    continue
                data = table.encode(values)
                self.backend.write(table.rva, data)  # type: ignore[union-attr]
                verify = self.backend.read(table.rva, table.byte_size)  # type: ignore[union-attr]
                if verify != data:
                    raise BackendError(f"Verification failed while restoring {table.title}.")
                self.live_values[table.key] = table.decode(verify)
                self.pending_values[table.key].clear()
            self._populate_tree()
            self._set_status("Restored all tables to their attach-time runtime snapshots", "good")
        except Exception as exc:
            self._show_error("Restore All Failed", exc)

    def _copy_current_bytes(self) -> None:
        table = self.current_table
        values = [self._effective_value(table, index) for index in range(table.size)]
        if any(value is None for value in values):
            messagebox.showwarning("No Data", "Connect to the game or load a preset first.")
            return
        raw = table.encode([int(value) for value in values if value is not None])
        text = " ".join(f"{byte:02X}" for byte in raw)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status(f"Copied {table.byte_size} raw bytes from {table.title}", "good")

    def _paste_table_bytes(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Paste Bytes — {self.current_table.title}")
        dialog.geometry("720x300")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, style="Panel.TFrame", padding=14)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(
            frame,
            text=(
                f"Paste either {self.current_table.byte_size} raw bytes or "
                f"{self.current_table.size} element values. Raw bytes use little-endian order. "
                "Accepted forms: hex pairs, 0x-prefixed values, or decimal lists."
            ),
            style="Panel.TLabel",
            wraplength=650,
        ).pack(anchor="w", pady=(0, 8))
        text_box = tk.Text(
            frame,
            height=8,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#245d87",
            relief="flat",
            wrap="word",
        )
        text_box.pack(fill="both", expand=True)

        def stage() -> None:
            try:
                values = self._parse_table_sequence(
                    text_box.get("1.0", "end"), self.current_table
                )
                live = self.live_values.get(self.current_table.key)
                pending = self.pending_values[self.current_table.key]
                pending.clear()
                for index, value in enumerate(values):
                    self._validate_kind(self.current_table.value_kind, value)
                    if live is None or live[index] != value:
                        pending[index] = value
                dialog.destroy()
                self._populate_tree()
                self._set_status(
                    f"Staged {len(pending)} differing value(s) in {self.current_table.title}",
                    "warn",
                )
            except Exception as exc:
                messagebox.showerror("Invalid Byte Array", str(exc), parent=dialog)

        controls = ttk.Frame(frame, style="Panel.TFrame")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Cancel", command=dialog.destroy).pack(side="right", padx=3)
        ttk.Button(controls, text="Stage Values", style="Accent.TButton", command=stage).pack(side="right", padx=3)
        text_box.focus_set()

    @staticmethod
    def _parse_table_sequence(text: str, table: TableDefinition) -> List[int]:
        stripped = text.strip()
        if not stripped:
            raise ValueError("No values were pasted.")

        tokens = [token for token in re.split(r"[\s,;]+", stripped) if token]

        # One contiguous hex string always represents raw table bytes.
        if (
            len(tokens) == 1
            and re.fullmatch(r"[0-9A-Fa-f]+", tokens[0])
            and len(tokens[0]) == table.byte_size * 2
        ):
            return table.decode(bytes.fromhex(tokens[0]))

        # For multi-byte tables, exactly one token per row is interpreted as values.
        if table.element_width > 1 and len(tokens) == table.size:
            values: List[int] = []
            for token in tokens:
                value = int(token, 16) if token.lower().startswith("0x") else int(token, 10)
                if not 0 <= value <= table.max_value:
                    raise ValueError(f"Value '{token}' is outside 0–{table.max_value}.")
                values.append(value)
            return values

        # Otherwise parse an exact raw-byte sequence and decode it by table width.
        if len(tokens) != table.byte_size:
            raise ValueError(
                f"Expected either {table.size} table values or {table.byte_size} raw bytes, "
                f"but received {len(tokens)} token(s)."
            )
        all_two_digit_hex = all(re.fullmatch(r"[0-9A-Fa-f]{2}", token) for token in tokens)
        raw_values: List[int] = []
        for token in tokens:
            if token.lower().startswith("0x"):
                value = int(token, 16)
            elif all_two_digit_hex:
                value = int(token, 16)
            else:
                value = int(token, 10)
            if not 0 <= value <= 255:
                raise ValueError(f"Raw byte '{token}' is outside 0–255.")
            raw_values.append(value)
        return table.decode(bytes(raw_values))

    def _export_preset(self) -> None:
        data = self._build_preset_data(use_effective=True)
        path = filedialog.asksaveasfilename(
            title="Export Warcraft II table preset",
            defaultextension=".json",
            filetypes=(("JSON preset", "*.json"), ("All files", "*.*")),
            initialfile="War2_Remastered_Tables.json",
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._set_status(f"Exported preset to {path}", "good")
        except Exception as exc:
            self._show_error("Export Failed", exc)

    def _save_snapshot(self) -> None:
        if not self.original_values:
            messagebox.showwarning("No Snapshot", "Attach to the running Warcraft II process first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save attach-time runtime snapshot",
            defaultextension=".json",
            filetypes=(("JSON snapshot", "*.json"), ("All files", "*.*")),
            initialfile="War2_Remastered_Original_Snapshot.json",
        )
        if not path:
            return
        try:
            data = self._build_preset_data(use_effective=False, source=self.original_values)
            data["kind"] = "connection_snapshot"
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._set_status(f"Saved snapshot to {path}", "good")
        except Exception as exc:
            self._show_error("Snapshot Save Failed", exc)

    def _build_preset_data(
        self,
        use_effective: bool,
        source: Optional[Mapping[str, Sequence[int]]] = None,
    ) -> dict:
        output = {
            "format": "war2_remastered_table_editor",
            "version": 1,
            "application_version": APP_VERSION,
            "kind": "preset",
            "tables": {},
        }
        for table in TABLES:
            if source is not None:
                raw_values = source.get(table.key)
                if raw_values is None:
                    continue
                values = list(raw_values)
            elif use_effective:
                values = []
                for index in range(table.size):
                    value = self._effective_value(table, index)
                    if value is None:
                        break
                    values.append(value)
                if len(values) != table.size:
                    continue
            else:
                raw_values = self.live_values.get(table.key)
                if raw_values is None:
                    continue
                values = list(raw_values)
            output["tables"][table.key] = {
                "title": table.title,
                "rva": f"0x{table.rva:08X}",
                "element_width": table.element_width,
                "values": values,
            }
        return output

    def _import_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Warcraft II table preset",
            filetypes=(("JSON preset", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            tables_data = data.get("tables")
            if not isinstance(tables_data, dict):
                raise ValueError("Preset does not contain a 'tables' object.")

            staged = 0
            loaded_tables = 0
            for key, payload in tables_data.items():
                table = TABLE_BY_KEY.get(key)
                if table is None:
                    continue
                values = payload.get("values") if isinstance(payload, dict) else payload
                if not isinstance(values, list):
                    raise ValueError(f"Table '{key}' does not contain a values list.")
                if len(values) != table.size:
                    raise ValueError(
                        f"Table '{key}' expected {table.size} values, found {len(values)}."
                    )
                parsed = []
                for value in values:
                    if not isinstance(value, int) or not 0 <= value <= table.max_value:
                        raise ValueError(
                            f"Table '{key}' contains a value outside 0–{table.max_value}: {value!r}"
                        )
                    self._validate_kind(table.value_kind, value)
                    parsed.append(value)

                live = self.live_values.get(key)
                pending = self.pending_values[key]
                pending.clear()
                for index, value in enumerate(parsed):
                    if live is None or live[index] != value:
                        pending[index] = value
                staged += len(pending)
                loaded_tables += 1

            if loaded_tables == 0:
                raise ValueError("The preset did not contain any recognized tables.")
            self._populate_tree()
            self._set_status(f"Imported {loaded_tables} table(s); staged {staged} differing byte(s)", "warn")
        except Exception as exc:
            self._show_error("Import Failed", exc)

    def _require_backend(self) -> None:
        if self.backend is None:
            raise BackendError("Attach to the running Warcraft II process first.")

    def _show_error(self, title: str, exc: Exception) -> None:
        self._set_status(f"{title}: {exc}", "bad")
        messagebox.showerror(title, str(exc), parent=self)

    def report_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self._set_status(f"Unexpected error: {exc_value}", "bad")
        messagebox.showerror("Unexpected Error", f"{exc_value}\n\n{details[-2500:]}", parent=self)

    def _on_close(self) -> None:
        if self.backend is not None:
            self.backend.close()
        self.destroy()


def dependency_message() -> Optional[str]:
    if pymem is not None:
        return None
    return (
        "Missing package: pymem.\n\n"
        "Run Start_Table_Editor.bat, or install it with:\n"
        f"{sys.executable} -m pip install pymem\n\n"
        "Runtime attach is unavailable until Pymem is installed."
    )


def main() -> int:
    app = War2TableEditor()
    notice = dependency_message()
    if notice:
        app.after(250, lambda: messagebox.showwarning("Dependencies", notice, parent=app))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
