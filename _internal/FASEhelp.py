"""Central help text for Immortal Champions / FASE UX and launcher.

Edit this file when gameplay help changes. Runtime screens should import
``get_help_lines`` through the stable ``FASEhelp`` wrapper instead of carrying
local copies of the help text.
"""
from __future__ import annotations

from typing import Iterable, Optional

DEFAULT_WIN_MAJORITY = 90.0
DEFAULT_DIVINE_ASCENDANCY = 90.0
DEFAULT_DEFEAT_PCT = 1.0
DEFAULT_POP_FLOOR = 1_000

HELP_TEMPLATE: list[str] = ['======================================================================', '                           IMMORTAL CHAMPIONS', '======================================================================', 'The Fantasy Antfarm Simulator/Engine (FASE) is a living fantasy simulation.', "The procedurally generated continent of 'Atlwier' is divided into multiple", 'regions fully populated with commoners and adventurers that produce food,', 'wealth, faith, instability, heroes, kingdoms, monsters, legends, and ruins.', '', "'Immortal Champions' is the interactive game layer that runs on top of FASE.", 'In it, you assume the role of a god seeking to dominate Atlwier with your', 'divine influence. You can create champions and through them attempt to convert', 'the population to worship you. However, you are not the only god in the pantheon', 'and your rivals will stop at nothing to assert their own dominance on Atlwier.', '', 'TL;DR: You cannot directly interact with the world. You may only influence it.', 'Influence is your source of power and souls are your currency.', '(see below for more on Player-God mechanics)', '', '', 'Order reflects regional stability:', '  - high order  -> prosperity and growth', '  - low order   -> unrest, raids, collapse, corruption', '', 'Polities rise and fall dynamically through war, succession, diplomacy,', 'religion, monster pressure, and inheritance.', '', 'ADVENTURERS', '-----------', 'Adventurers emerge from the population and form parties.', '', 'Classes:', '  Fighter  - frontline warrior and commander', '  Warden   - scout, hunter, skirmisher', '  Wizard   - rare arcane specialist', '  Bard     - support, recovery, inspiration, lore', '', 'Adventurers gain:', '  - levels', '  - reputation', '  - rivals', '  - spouses', '  - best friends', '  - dynasties', '  - kill records', '', 'High-reputation adventurers may:', '  - found kingdoms', '  - train students', '  - wield relics', '  - become champions', '  - shape world history', '  - inspire myth and legend', '  - the rare few will be diefied and enter the pantheon as gods', '', 'Older adventurers eventually retire from active combat but continue', 'to influence society.', '', 'PARTIES & KINGDOMS', '------------------', 'Parties are independent adventuring groups.', '', 'Successful parties may:', '  - establish strongholds', '  - found kingdoms', '  - absorb weaker realms', '  - create dynasties', '', 'Kingdoms may:', '  - ally', '  - trade', '  - wage war', '  - fracture', '  - merge through inheritance', '', 'Children of two rulers may inherit multiple kingdoms and unite them', 'into a larger realm.', '', 'SCHOOLS', '-------', 'Schools train the children of adventurers into future adventurers.', '', 'School prestige increases through:', '  - successful graduates', '  - experienced teachers', '  - long institutional survival', '', 'Prestigious schools produce stronger adventurers.', '', 'GODS & RELIGION', '---------------', 'Faith influences the entire world.', '', 'Base gods:', '  - Lord of Light (good)', '  - Lord of Darkness (evil)', '  - God of Chance (neutral, fate)', '', 'The user may create and guide a custom god.', '', 'Gods gain influence through living followers.', '', 'Souls may be spent to:', '  - create champions to wander the realm and do deeds in your name', '  - forge relics your champions can wield to gain power and reputation', '  - bless followers with boons that improve stats for 1 season', '  - target enemies and the faithful of your rivals', '  - influence regions by sending followers to stabilize/destabilize order', '  - launch holy wars', '', 'RELICS', '------', 'Relics are powerful artifacts that grant permanent boons when wielded.', '  - User-gods can create their own relics.', '  - There are also some relics baked into the game that are very', '    powerful and can forge or destroy kingdoms.', '', 'Relics may:', '  - empower champions', '  - reshape wars', '  - attract monsters', '  - become objects of legend', '  - change the fate of a region or ruler', '  - be protected by difficult guardians... monsters', '', 'MONSTER TYPES', '--------', 'Goblin', '  - Fast-breeding raiders that thrive in instability.', '  - life span simliar to humans', '  - can be influenced by evil actors', '', 'Giants', '  - Territorial regional threats capable of devastating settlements.', '  - several types with different agendas and behaviors', '', 'Dragon', '  - Long-lived apex predators.', '  - Benevolent dragons may protect civilization.', '  - Other dragons may dominate or terrorize regions.', '', 'Ancient Horror', '  - Extremely rare world-level catastrophes.', '  - Horrors emerge only under severe world conditions or dark rituals.', '  - They cannot truly be killed -- only banished.', '', 'PLAYER GOD GOALS', '----------------', 'Expand your faith and maintain influence through:', '  - champions', '  - kingdoms', '  - relics', '  - diplomacy', '  - war', '  - stability', '  - mortal loyalty', '', 'WIN / LOSS CONDITIONS', '---------------------', 'Mortal Majority ({win_majority:.0f}%)', '  - A single faith controls this share of living mortals.', '', 'Divine Ascendancy ({divine_pct:.0f}%)', '  - A deity reaches this share of total influence.', '', 'Population Collapse (<{pop_floor})', '  - Civilization falls below sustainable population.', '', 'Extinction', '  - No living adventurers remain.', '', 'Player-God Defeat (<{defeat_pct:.1f}% influence)', '  - Your faith collapses below viable influence.', '', 'NOTES', '-----', '- Unpaused, the simulation continues even without player intervention.', '- Every actor, kingdom, relic, and monster has persistent history.', '- A majority of the population (commoners) tracked as an aggregate pool', '- Long runs may produce entirely different civilizations and legends.', '- No two seeds evolve the same way.', '- Sim can run slow when population gets very high. Especially', '  after a few centuries. To improve speed:', '  - Run with event log expanded (F2).', '  - Set ticks/frame to 1x (+ or - key to change frame rate)', '  - The simulation can be run headless (no god play or UI) if you just want', '    to see a world live. If this appeals to you, I recommend running FASE.py,', '    directly from a command prompt (headless). ', '  - IF you do run it headless, I highly recommend running with Pypy', '', 'KEYBINDS', '--------', 'GLOBAL', '------', 'SPACE  pause/run', '+/-    speed', '1,2,3  1x, 5x, 20x speed', 'F5/F9  save/load', 'a      audio menu', 'q      quit', 'h      help', '', 'VIEWS', '-----', 'c      cartography / region dossier', 'v      order/religion', 'u      summaries', 'g      god UI', 'm      monster inspector', 'j      journal', '/      actor search', '', 'MAP / ACTOR LIST', '----------------', 'ARROWS  select region', 'PgUp/PgDn select actor in current region', 'Home/End first/last actor in current region', 'Enter/i inspect selected actor', '', 'ACTOR INSPECTOR', '---------------', 'i/Esc   close inspector', 'P       promote champion', 'Y       story character', 'T       target', 'X       cancel target', '', 'GOD UI', '------', 'TAB     page', 'f/z     sort/reverse', 'P       promote champion', 'r       relic', 'B       boon', 'T       target', 'X       cancel target', 'W       holy war', 'S       move school', 'L/D     stabilize/destabilize']

def _coerce_number(value, default: float) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def get_help_lines(
    *,
    win_majority: Optional[float] = None,
    divine_pct: Optional[float] = None,
    defeat_pct: Optional[float] = None,
    pop_floor: Optional[int] = None,
) -> list[str]:
    """Return formatted help text as a list of display lines.

    Callers may pass current config constants. Defaults keep the help screen
    usable even if imported outside the full simulator runtime.
    """
    values = {
        "win_majority": _coerce_number(win_majority, DEFAULT_WIN_MAJORITY),
        "divine_pct": _coerce_number(divine_pct, DEFAULT_DIVINE_ASCENDANCY),
        "defeat_pct": _coerce_number(defeat_pct, DEFAULT_DEFEAT_PCT),
        "pop_floor": int(_coerce_number(pop_floor, DEFAULT_POP_FLOOR)),
    }
    out: list[str] = []
    for line in HELP_TEMPLATE:
        try:
            out.append(str(line).format(**values))
        except Exception:
            out.append(str(line))
    return out


__all__ = ["HELP_TEMPLATE", "get_help_lines"]
