from typing import List, Tuple
from FASEclass import Role

# ===========================================================================
# SIMULATION CLOCK — DO NOT CHANGE
# Changing these values can break calendar/time assumptions.
# ===========================================================================
TICKS_PER_DAY = 4
TICKS_PER_YEAR = TICKS_PER_DAY * 360
TICKS_PER_TENDAY = TICKS_PER_DAY * 10
TICKS_PER_MONTH = TICKS_PER_DAY * 30
TICKS_PER_SEASON = TICKS_PER_DAY * 90

# ===========================================================================
# RUN DEFAULTS
# ===========================================================================
DEFAULT_SEED = None
DEFAULT_YEARS = "indef"
VERBOSE_EVENT_IMPORTANCE = 1

# ===========================================================================
# OUTPUT / REPORTING
# Master switches for generated reports and data exports. These are output
# controls only; they should not change simulation mechanics.
# start_game may override these per run via FANTFARM_* environment variables.
# ===========================================================================
SUMMARY_ENABLED = True
LEGENDARIUM_ENABLED = False
CSV_EXPORTS_ENABLED = False
CSV_METRICS_ENABLED = False
CSV_HISTORY_ENABLED = False
CSV_EVENTS_ENABLED = False


# ===========================================================================
# SUMMARY OUTPUT SECTIONS
# These control sections inside the generated summary report. They do not
# disable simulation mechanics or CSV/legendarium exports.
# ===========================================================================
SUMMARY_RUN_METRICS_ENABLED = True
SUMMARY_DEMOGRAPHICS_ENABLED = True
SUMMARY_COMMONER_DEATH_BREAKDOWN_ENABLED = True
SUMMARY_WORLD_CONDITION_ENABLED = True
SUMMARY_ADVENTURER_LISTS_ENABLED = False
SUMMARY_NOTABLE_BIRTHS_ENABLED = False
SUMMARY_NOTABLE_DEATHS_ENABLED = False
SUMMARY_NOTABLE_FEATS_ENABLED = False
SUMMARY_RECENT_RETIREMENTS_ENABLED = False
SUMMARY_MAIN_CHARACTER_ACTIONS_ENABLED = True
SUMMARY_LORE_ENABLED = True
SUMMARY_RELIC_HISTORY_ENABLED = True
SUMMARY_MONSTER_ACTIVITY_ENABLED = True
SUMMARY_PARTY_ACTIVITY_ENABLED = False
SUMMARY_POLITICAL_ACTIVITY_ENABLED = True
SUMMARY_ECONOMY_ENABLED = True
SUMMARY_HISTORY_GRAPHS_ENABLED = True
SUMMARY_PARENTAGE_AUDIT_ENABLED = False
SUMMARY_HOLY_WAR_ENABLED = True
SUMMARY_IMMORTAL_ACTIONS_ENABLED = True
SUMMARY_LORE_PROFILER_ENABLED = True

# ===========================================================================
# LEGENDARIUM OUTPUT SECTIONS
# These only control what is written to the legendarium report. They do not
# disable the underlying lore, bard, cult, religion, or monster systems.
# ===========================================================================
LEGENDARIUM_LIVING_AUTHORITY_ENABLED = True
LEGENDARIUM_RELIGIOUS_CATALYSTS_ENABLED = True
LEGENDARIUM_REMEMBERED_FIGURES_ENABLED = True
LEGENDARIUM_PROTO_CULTS_ENABLED = True
LEGENDARIUM_TOP_SONGS_ENABLED = True
LEGENDARIUM_CULTURAL_MEMORY_ENABLED = True
LEGENDARIUM_SONGS_AND_MEMORY_ENABLED = True
LEGENDARIUM_HYMNS_ENABLED = True
LEGENDARIUM_RELIC_MONSTER_FOLKLORE_ENABLED = True
LEGENDARIUM_FAITH_DOUBT_ENABLED = True

# ===========================================================================
# WORLD SIZE / REGIONS / POPULATION
# General rule of thumb for minimum viable population: at least (region count) * 875.
# ===========================================================================
REGION_COUNT = 11
INITIAL_POPULATION = 12000
HARDSHIP_DEATH_RATE_MULTIPLIER = 0.1
REGION_SIZE_MIN = 0.75
REGION_SIZE_MAX = 1.25
PLAINS_CAP_MIN = 1_500_000
PLAINS_CAP_MAX = 2_500_000
FOREST_CAP_MIN = 1_000_000
FOREST_CAP_MAX = 2_000_000
HIGHLANDS_CAP_MIN = 500_000
HIGHLANDS_CAP_MAX = 1_500_000
PREGNANCY_DURATION_TICKS = TICKS_PER_MONTH * 9
COMMONER_PREGNANCY_MONTHS = 9
COMMONER_MONTHLY_PREGNANCY_RATE = 0.006

# ===========================================================================
# HISTORIAN / EVENT ARCHIVE
# start_game can override several of these per run via FANTFARM_* environment variables.
# ===========================================================================
HISTORIAN_ENABLED = True
EVENT_MEMORY_LIMIT = 1000
HISTORIAN_FLUSH_EVENT_COUNT = 5000
HISTORIAN_MIN_IMPORTANCE = 2
HISTORIAN_ARCHIVE_ALL = False
HISTORIAN_FORCE_CATEGORIES = {
    "world", "monthly", "seasonal", "notable_death", "champion_death",
    "legacy_birth", "coming_of_age", "retirement", "polity", "polity_challenge",
    "succession", "party", "party_coup", "party_split", "monster_spawn",
    "legendary_monster_kill", "necromancer_crisis", "holy_war", "god_death",
    "relic", "relic_quest", "relic_pressure", "adventurer_school", "refugees",
    "diplomacy", "corruption",
}
HISTORIAN_SUMMARY_LOOKBACK_TICKS = TICKS_PER_YEAR
HISTORIAN_SUMMARY_EVENT_LIMIT = 3000

# ===========================================================================
# ENDGAME / WIN-LOSS PRESSURE
# ===========================================================================
ENDGAME_POPULATION_FLOOR = 1000
ENDGAME_INFLUENCE_LOSS_THRESHOLD = 5.0
ENDGAME_INFLUENCE_WIN_THRESHOLD = 90.0
ENDGAME_MAJORITY_CONTROL_THRESHOLD = 90.0

# ===========================================================================
# IMMORTAL ECONOMY / RELICS / CHAMPIONS
# ===========================================================================
IMMORTAL_SOUL_CAP = 3000
PANTHEON_MAX_ACTIVE_GODS = 7
LESSER_RELIC_SOUL_COST = 75
GREATER_RELIC_SOUL_COST = 125
PLAYER_LESSER_RELIC_LIMIT = 2
PLAYER_GREATER_RELIC_LIMIT = 1
CREATED_RELIC_RECLAIM_CHANCE = 0.99
CREATED_RELIC_RIVAL_CLAIM_CHANCE = 0.70
STARTING_CHAMPION_GRACE_YEARS = 2
DIVINE_CHAMPION_COOLDOWN_TICKS = TICKS_PER_YEAR * 3
CHAMPION_ACTIVE_CONVERSION_RATE = 0.0001
CHAMPION_ACTIVE_CONVERSION_MIN = 5
CHAMPION_ACTIVE_CONVERSION_MAX = 250

# ===========================================================================
# IMMORTAL HOLY WAR / DOMINANCE / DISASTERS
# ===========================================================================
HOLY_WAR_MIN_ATTACKER_INFLUENCE = 30.0
HOLY_WAR_MAX_TARGET_INFLUENCE = 20.0
HOLY_WAR_SOUL_COST = 150
HOLY_WAR_COOLDOWN_YEARS = 7
HOLY_WAR_MAX_FOLLOWER_LOSS_RATE = 0.55
HOLY_WAR_GOD_KILL_TARGET_THRESHOLD = 2.0
IMMORTAL_DOMINANCE_BLEED_THRESHOLD = 65.0
IMMORTAL_DOMINANCE_BLEED_RATE = 0.010
IMMORTAL_DOMINANCE_EXCESS_MULTIPLIER = 0.060
IMMORTAL_PRESSURE_MAX_REGIONS = 5
IMMORTAL_DESPERATION_THRESHOLD = 5.0
IMMORTAL_DISASTER_COOLDOWN_TICKS = TICKS_PER_YEAR * 2
IMMORTAL_DISASTER_MAX_REGIONS = 3
IMMORTAL_DISASTER_BASE_SHAKE = 0.08
IMMORTAL_DISASTER_EXCESS_MULTIPLIER = 0.18
IMMORTAL_DISASTER_MAX_SHAKE = 0.28
IMMORTAL_DISASTER_SHIELD_CAP = 0.70

# ===========================================================================
# DIVINE DIRECTIVES / GOD STATE MAINTENANCE
# ===========================================================================
DIVINE_TARGET_SOUL_COST = 75
DIVINE_REGION_DIRECTIVE_SOUL_COST = 25
DIVINE_DIRECTIVE_EXPIRATION_TICKS = TICKS_PER_YEAR
DIVINE_MAINTENANCE_INTERVAL_TICKS = TICKS_PER_DAY * 7
GOD_STATE_REFRESH_INTERVAL_TICKS = DIVINE_MAINTENANCE_INTERVAL_TICKS
DIVINE_DIRECTIVE_CHAMPION_ACCEPT_BONUS = 0.45
DIVINE_DIRECTIVE_FOLLOWER_ACCEPT_BONUS = 0.20
DIVINE_STABILIZE_ORDER_DELTA = 10
DIVINE_STABILIZE_CONTROL_DELTA = 3
DIVINE_DESTABILIZE_ORDER_DELTA = -10
DIVINE_DESTABILIZE_CONTROL_DELTA = -3

# ===========================================================================
# PUBLIC RELIGIOUS CONVERSION
# ===========================================================================
RELIGIOUS_CONVERSION_REGION_COOLDOWN_TICKS = TICKS_PER_MONTH
RELIGIOUS_FAVORED_CONVERSION_RATE = 0.003
RELIGIOUS_HERO_CONVERSION_RATE = 0.0015
ADVENTURER_DEITY_CONVERSION_COOLDOWN_TICKS = TICKS_PER_MONTH * 2

# ===========================================================================
# FAITH DOUBT / PROTOCULT MEMBERSHIP
# ===========================================================================
FAITH_DOUBT_DECAY_PER_DRIFT = 0.97
PROTOCULT_MEMBERSHIP_MIN_AFFINITY = 0.15
PROTOCULT_MEMBERSHIP_SWITCH_MARGIN = 0.12
PROTOCULT_MEMBERSHIP_RETENTION_FLOOR = 0.04
CULT_SCHOOL_CLEANUP_INTERVAL_TICKS = TICKS_PER_MONTH
RELIGIOUS_DRIFT_ENABLED = True
RELIGIOUS_DRIFT_INTERVAL_TICKS = TICKS_PER_MONTH
CULT_AFFINITY_MIN_DOUBT = 0.08

# ===========================================================================
# OPEN WORSHIP LEGACY BRIDGE
# ===========================================================================
OPEN_WORSHIP_ENABLED = True
OPEN_WORSHIP_CHECK_INTERVAL_TICKS = TICKS_PER_YEAR
OPEN_WORSHIP_MIN_AFFINITY = 0.85
OPEN_WORSHIP_MIN_DOUBT = 0.25
OPEN_WORSHIP_MIN_REGIONS = 2
OPEN_WORSHIP_MIN_LEGEND_PRESSURE = 2500.0
OPEN_WORSHIP_MIN_MYTHIC_LEGACY = 350.0
OPEN_WORSHIP_BASE_CHANCE = 0.06
OPEN_WORSHIP_MAX_CHANCE = 0.35
OPEN_WORSHIP_FAMOUS_BARD_REP = 60
OPEN_WORSHIP_FAMOUS_ACTOR_REP = 90

# ===========================================================================
# APOTHEOSIS / EMERGENT PANTHEON ELEVATION
# Hidden cult growth happens before declaration. Successful declaration immediately creates a pantheon god.
# ===========================================================================
APOTHEOSIS_ENABLED = True
APOTHEOSIS_CHECK_INTERVAL_TICKS = TICKS_PER_YEAR
APOTHEOSIS_MIN_AFFINITY = 0.50
APOTHEOSIS_MIN_DOUBT = 0.20
APOTHEOSIS_MIN_CLOUT = 180.0
APOTHEOSIS_MIN_DECLARATION_SCORE = 420.0
APOTHEOSIS_MIN_CULT_MEMBERS = 12
APOTHEOSIS_MIN_CULT_AFFINITY_MASS = 4.0
APOTHEOSIS_MIN_LEGEND_PRESSURE = 60.0
APOTHEOSIS_MIN_MYTHIC_LEGACY = 220.0
APOTHEOSIS_MIN_REGIONS = 2
APOTHEOSIS_MIN_CULT_AGE_YEARS = 3
APOTHEOSIS_BASE_CHANCE = 0.04
APOTHEOSIS_MAX_CHANCE = 0.35
APOTHEOSIS_DECLARATION_SCORE_DIVISOR = 1800.0
APOTHEOSIS_STARTING_SOULS = 150
APOTHEOSIS_CONVERTED_ACTOR_CONVICTION = 70

# ===========================================================================
# APOTHEOSIS CONVERSION WAVE
# ===========================================================================
APOTHEOSIS_ACTOR_BASE_CONVERSION_CHANCE = 0.12
APOTHEOSIS_ACTOR_AFFINITY_WEIGHT = 0.62
APOTHEOSIS_ACTOR_DOUBT_WEIGHT = 0.18
APOTHEOSIS_ACTOR_CLOUT_BONUS_CAP = 0.12
APOTHEOSIS_ACTOR_LOCKED_MAX_CHANCE = 0.03
APOTHEOSIS_ACTOR_CHAMPION_MAX_CHANCE = 0.12
APOTHEOSIS_COMMONER_BASE_CONVERSION_RATE = 0.02
APOTHEOSIS_COMMONER_LATENT_MULT = 0.80
APOTHEOSIS_COMMONER_FOUNDER_REGION_BONUS = 0.06
APOTHEOSIS_COMMONER_POLITY_REGION_BONUS = 0.04
APOTHEOSIS_COMMONER_MAX_REGION_RATE = 0.45

# ===========================================================================
# ADVENTURER SCHOOLS
# ===========================================================================
SCHOOL_TEACHER_BONUS_CAP = 10
SCHOOL_BASE_CAPACITY = 50
SCHOOL_CAPACITY_TOP_RANK_MULTIPLIER = 3.0
SCHOOL_CAPACITY_SECOND_RANK_MULTIPLIER = 2.0
SCHOOL_CAPACITY_THIRD_RANK_MULTIPLIER = 1.5
SCHOOL_COMBAT_TRAINING_MIN_AGE = 10
SCHOOL_COMBAT_TRAINING_MAX_AGE = 16
SCHOOL_FIRST_IN_CLASS_XP_BONUS = 75
SCHOOL_BASE_XP_BONUS = 25
SCHOOL_XP_PER_TEACHER_BONUS = 15
SCHOOL_STAT_BONUS_CHANCE_PER_TEACHER_BONUS = 0.03
SCHOOL_FIRST_IN_CLASS_TEACHER_SCORE_BONUS = 2
SCHOOL_PRESTIGE_CAP_YEARS = 50
SCHOOL_XP_PER_PRESTIGE_YEAR = 2
SCHOOL_STAT_BONUS_CHANCE_PER_PRESTIGE_YEAR = 0.004
SCHOOL_DEITY_ABBREVIATIONS = {}
SCHOOL_MOVE_COOLDOWN_YEARS = 10
SCHOOL_PRESTIGE_CAP = 100
SCHOOL_PRESTIGE_PER_YEAR = 1

# ===========================================================================
# ADVENTURER ACTIONS / REST / SOCIAL MEMORY
# ===========================================================================
ACTIONS_PER_TICK = 1
COMBAT_COOLDOWN_TICKS = TICKS_PER_DAY
# Event-worthy actions consume fictional time.  Cooldowns prevent immediate
# re-announcement; repeat factors make actors increasingly likely to change
# tactics without hard-forbidding stubborn repeats.
ACTION_COOLDOWN_DEFAULT_TICKS = TICKS_PER_TENDAY
ACTION_COOLDOWN_TICKS_BY_TYPE = {
    "break_resistance": TICKS_PER_TENDAY,
    "oppress_commoners": TICKS_PER_TENDAY,
    "raise_wards": TICKS_PER_MONTH,
    "disrupt_capture": TICKS_PER_TENDAY,
    "protect_commoners": TICKS_PER_TENDAY,
    "travel": TICKS_PER_DAY * 5,
    "retreat": TICKS_PER_TENDAY + TICKS_PER_DAY * 5,
    "recover": TICKS_PER_TENDAY,
}
ACTION_REPEAT_FACTORS = {
    0: 1.00,
    1: 0.80,
    2: 0.55,
    3: 0.30,
    4: 0.15,
}
ACTION_REPEAT_MIN_FACTOR = 0.05
ACTION_REPEAT_STUBBORN_BONUS = 0.15
ACTION_REPEAT_PATIENT_BONUS = 0.10
ACTION_REPEAT_IMPULSIVE_PENALTY = 0.15
ACTION_REPEAT_COWARDLY_PENALTY = 0.10
ACTION_SUCCESS_RESETS_REPEAT = True
ADVENTURER_SHIFT_COUNT = 6
POST_BATTLE_REST_MIN = TICKS_PER_DAY * 4
POST_BATTLE_REST_MAX = TICKS_PER_DAY * 12
POST_ROUT_REST_MIN = TICKS_PER_DAY * 8
POST_ROUT_REST_MAX = TICKS_PER_DAY * 24
SHORT_REST_FATIGUE_THRESHOLD = 3
LONG_REST_FATIGUE_THRESHOLD = 6
SHORT_RESTS_BEFORE_LONG = 2
SHORT_REST_MIN = TICKS_PER_DAY * 2
SHORT_REST_MAX = TICKS_PER_DAY * 6
LONG_REST_MIN = TICKS_PER_TENDAY
LONG_REST_MAX = TICKS_PER_MONTH
MAX_REVENGE_TARGETS = 3
MAX_FRIENDS = 5
REVENGE_BOON_DURATION_TICKS = TICKS_PER_YEAR
WIZARD_PROMOTION_CHANCE = 0.05

# ===========================================================================
# ADVENTURER RECOVERY PRESSURE
# ===========================================================================
RECOVERY_ADVENTURER_CRISIS_THRESHOLD = 50
RECOVERY_ADVENTURER_LOW_THRESHOLD = 120
RECOVERY_PARTYLESS_BONUS = 0.25

# ===========================================================================
# MONSTER CAPS / GRACE / COMMONER DAMAGE
# ===========================================================================
MAX_WILD_GIANTS = 3
MAX_WILD_DRAGONS = 1
MONSTER_GRACE_YEARS = 7
MONSTER_GRACE_VARIANCE = 2
MONSTER_COMMONER_DEATH_MULTIPLIER = 0.15
DRAGON_COMMONER_DEATH_FRACTION = 0.10
MONSTER_SCATTER_MULTIPLIER_BY_KIND = {
    "Goblin": (2, 8),
    "Giant": (5, 25),
    "Dragon": (10, 50),
    "Ancient Horror": (25, 100),
}
MONSTER_SCATTER_CAP_BY_KIND = {
    "Goblin": 20,
    "Giant": 60,
    "Dragon": 100,
    "Ancient Horror": 250,
}

# ===========================================================================
# DRAGONS
# ===========================================================================
DRAGON_DORMANCY_ENABLED = True
DRAGON_DORMANCY_POP_THRESHOLD = 0.20
DRAGON_WAKE_POP_THRESHOLD = 1.1
DRAGON_RAID_RATE_BONUS = 0.0005
DRAGON_REPRO_CHANCE = 0.00025
BENEVOLENT_DRAGONS = {"White", "Blue"}
AMBIVALENT_DRAGONS = {"Green", "Red"}
CHROMATIC_DRAGONS = ["Red", "Blue", "Green", "Black", "White", "Metallic", "Purple"]
DRAGON_ATTRACTION_MIN_REGIONS = 3
DRAGON_ATTRACTION_MIN_COMMONERS = 400
DRAGON_ATTRACTION_COOLDOWN_TICKS = TICKS_PER_MONTH * 2

# ===========================================================================
# DRAGON-GIANT RIVALRY
# Species-level hatred. Dragon temperament and giant human-facing alignment do
# not apply here: all dragons hate all giants, and all giants hate all dragons.
# ===========================================================================
DRAGON_GIANT_RIVALRY_ENABLED = True
DRAGON_GIANT_RIVALRY_CHECK_TICKS = TICKS_PER_TENDAY
DRAGON_GIANT_RIVALRY_SAME_REGION_CHANCE = 0.85
DRAGON_GIANT_RIVALRY_NEIGHBOR_SEEK_CHANCE = 0.35
DRAGON_GIANT_RIVALRY_LOSER_DEATH_BASE = 0.15
DRAGON_GIANT_RIVALRY_LOSER_RETREAT_CHANCE = 0.60
DRAGON_GIANT_RIVALRY_ORDER_DAMAGE = 2
DRAGON_GIANT_RIVALRY_COLLATERAL_COMMONER_RATE = 0.01
DRAGON_GIANT_RIVALRY_WINNER_XP = 3
DRAGON_GIANT_RIVALRY_COOLDOWN_TICKS = TICKS_PER_TENDAY

# ===========================================================================
# MONSTER COMBAT / REST / XP
# ===========================================================================
POST_MONSTER_REST_MIN = TICKS_PER_DAY * 6
POST_MONSTER_REST_MAX = TICKS_PER_DAY * 16
POST_LEGENDARY_REST_MIN = TICKS_PER_DAY * 20
POST_LEGENDARY_REST_MAX = TICKS_PER_MONTH * 2
MONSTER_AGE_POWER_STEP_TICKS = TICKS_PER_MONTH * 2
MONSTER_MAX_AGE_BONUS = 20
MONSTER_XP_POWER_STEP = 3
MONSTER_MAX_XP_BONUS = 15
MONSTER_LOW_HP_RETREAT_RATIO = 0.50
MONSTER_CRITICAL_HP_RETREAT_RATIO = 0.30
MONSTER_RETREAT_AVOID_RATIO = 1.25
MONSTER_RETREAT_COOLDOWN_MIN = 12
MONSTER_RETREAT_COOLDOWN_MAX = 36
MONSTER_SHORT_REST_MIN = 12
MONSTER_SHORT_REST_MAX = 36
MONSTER_LONG_REST_MIN = 48
MONSTER_LONG_REST_MAX = 144
MONSTER_POST_RAID_REST_MIN = 18
MONSTER_POST_RAID_REST_MAX = 54
MONSTER_TERROR_ORDER_DECAY_INTERVAL = 30
MONSTER_COMMONER_RAID_BASE = 0.012
MONSTER_COMMONER_RAID_SCALE = 0.0005
MONSTER_INFLUENCE_GOBLIN_PER_HEAD = 1
MONSTER_INFLUENCE_DRAGON = 12
MONSTER_XP_GOBLIN = 50
MONSTER_XP_GIANT = 250
MONSTER_XP_DRAGON = 875
MONSTER_XP_HORROR = 2500

# ===========================================================================
# MONSTER LIFESPANS / TYPES
# ===========================================================================
HORROR_UNIQUE = True
GIANT_TYPES = ["Hill Giant", "Stone Giant", "Frost Giant", "Green Giant"]
HORROR_TITLES = ["Whispering Maw", "Sleeper Below", "Many-Eyed Tide", "Void Saint", "Eldritch Terror", "The Nothing"]
GOBLIN_LIFESPAN_YEARS = (45, 110)
GIANT_LIFESPAN_YEARS = (160, 320)
DRAGON_LIFESPAN_YEARS = {
    "Blue": (500, 850),
    "Black": (500, 900),
    "Green": (600, 1000),
    "Red": (700, 1200),
    "Purple": (900, 1500),
    "White": (900, 1600),
    "Metallic": (1400, 2500),
}
MONSTER_OLD_AGE_GRACE_YEARS = 10
MONSTER_OLD_AGE_DEATH_CHANCE = 0.015
RECOVERY_MONSTER_SPAWN_SCALE_LOW = 0.45
RECOVERY_MONSTER_SPAWN_SCALE_CRISIS = 0.20
NEUTRAL_GIANT_WANDER_CHANCE = 0.03
NEUTRAL_GIANT_TERRITORY_CHANCE = 0.015

# ===========================================================================
# ANCIENT HORRORS
# ===========================================================================
ANCIENT_HORROR_CALENDAR = {
    "Whispering Maw": {"omen": (1, 11), "summon": (10, 11)},
    "Sleeper Below": {"omen": (2, 22), "summon": (11, 22)},
    "Many-Eyed Tide": {"omen": (3, 3), "summon": (12, 3)},
    "Void Saint": {"omen": (6, 6), "summon": (9, 6)},
    "Eldritch Terror": {"omen": (8, 18), "summon": (2, 18)},
    "The Nothing": {"omen": (12, 30), "summon": (6, 30)},
}
ANCIENT_HORROR_DOMINANCE_RATIO = 0.25
ANCIENT_HORROR_COOLDOWN_TICKS = 540
ANCIENT_HORROR_WORLD_COOLDOWN_TICKS = TICKS_PER_YEAR * 25
ANCIENT_HORROR_MAX_LIVING = 1
ANCIENT_HORROR_NATURAL_CHANCE_BY_DOMINANCE = [
    (0.75, 0.05),
    (0.60, 0.035),
    (0.50, 0.025),
    (0.40, 0.015),
    (0.25, 0.005),
]
ANCIENT_HORROR_SUMMON_MIN_LEVEL = 4
ANCIENT_HORROR_SUMMON_MIN_REP = 20
ANCIENT_HORROR_SUMMON_ATTEMPT_CHANCE = 0.13
ANCIENT_HORROR_SUMMON_SUCCESS_BASE = 0.45
ANCIENT_HORROR_SUMMON_PACT_BASE = 0.55
ANCIENT_HORROR_SUMMON_CASTER_DEATH_CHANCE = 0.33

# ===========================================================================
# ADVENTURER SURPLUS NECROMANCER CRISIS
# ===========================================================================
ADVENTURER_SURPLUS_NECROMANCER_ENABLED = True
ADVENTURER_SURPLUS_NECROMANCER_CHECK_MONTH = 6
ADVENTURER_SURPLUS_NECROMANCER_CHECK_DAY = 6
ADVENTURER_SURPLUS_NECROMANCER_RATIO = 0.04
ADVENTURER_SURPLUS_NECROMANCER_TARGET_RATIO = 0.018
ADVENTURER_SURPLUS_NECROMANCER_MIN_RATIO = 0.020
ADVENTURER_SURPLUS_NECROMANCER_COMMONER_COLLATERAL_RATE = 0.005
ADVENTURER_SURPLUS_NECROMANCER_CHANCE = 0.99
ADVENTURER_SURPLUS_NECROMANCER_COOLDOWN_YEARS = 6
ADVENTURER_SURPLUS_NECROMANCER_MONTHLY_PURGE_FRACTION = 0.16
ADVENTURER_SURPLUS_NECROMANCER_MIN_MONTHLY_KILLS = 5
ADVENTURER_SURPLUS_NECROMANCER_TITLES = [
    "The Black Widow",
    "The Pale Matron",
    "The Weeping Woman",
    "The Hollow Mother",
    "The Queen of Shadows",
    "The Bone Mother",
]

# ===========================================================================
# POLITY FOUNDING / CLAIMS / CHALLENGES
# ===========================================================================
POLITY_MIN_REPUTATION = 120
POLITY_MIN_PARTY_SIZE = 60
POLITY_REGION_CLAIM_MIN_REPUTATION = 80
POLITY_CHALLENGE_CHECK_TICKS = TICKS_PER_MONTH
POLITY_CHALLENGE_COOLDOWN_TICKS = TICKS_PER_YEAR // 2
EVIL_POLITY_EXTRA_CHALLENGE_PRESSURE = 0.05
POLITY_HIGH_STABILITY_CHALLENGE_SUPPRESSION = 0.45
POLITY_HIGH_LEGITIMACY_CHALLENGE_SUPPRESSION = 0.35
POLITY_MILITARY_SHIELD_PRESSURE_REDUCTION = 0.35
POLITY_MILITARY_SHIELD_SCORE_WEIGHT = 0.65
POLITY_STATE_LOYALTY_CHALLENGE_SUPPRESSION = 0.30
POLITY_CLAIMANT_MIN_REPUTATION = 90
POLITY_CLAIMANT_RULER_REP_FRACTION = 0.65
POLITY_CLAIMANT_POWER_MARGIN = 0.85
POLITY_DEPOSITION_CHANCE = 0.55
POLITY_FAILED_CHALLENGE_EXTRA_COOLDOWN_TICKS = TICKS_PER_YEAR // 3
POLITY_SUCCESSFUL_CHALLENGE_EXTRA_COOLDOWN_TICKS = TICKS_PER_YEAR

# ===========================================================================
# POLITY PENALTIES / SUCCESSION / RECOVERY
# ===========================================================================
FAILED_COUP_REP_LOSS = 18
FAILED_COUP_FAVOR_LOSS = 35
FAILED_ASSASSINATION_REP_LOSS = 12
FAILED_ASSASSINATION_FAVOR_LOSS = 30
FAILED_REVOLT_REP_LOSS = 10
FAILED_REVOLT_FAVOR_LOSS = 20
CROSS_POLITY_PARTY_FAVOR_LOSS = 6
CROSS_POLITY_PARTY_FAVOR_LOSS_FOLLOWER = 2
MIXED_POLITY_PARTY_LEADER_FAVOR_LOSS = 8
MIXED_POLITY_PARTY_FOLLOWER_FAVOR_LOSS = 3
SUCCESSION_GRACE_TICKS = TICKS_PER_YEAR
POLITY_GRACE_BLOCKS_EXPANSION = True
POLITY_GRACE_STABILITY_BONUS = 8
POLITY_GRACE_LEGITIMACY_BONUS = 6
POLITY_SUCCESSION_STATE_LOYALTY_WEIGHT = 2.0
POLITY_SUCCESSION_FAVOR_WEIGHT = 1.0
POLITY_SUCCESSION_DYNASTIC_BONUS = 45
POLITY_SUCCESSION_MILITARY_BONUS = 30
POLITY_SUCCESSION_PREVIOUS_APPROVAL_WEIGHT = 0.8
POLITY_SUCCESSION_PERSONAL_LOYALTY_THRESHOLD = 55
ASSASSINATION_GUARD_PER_PARTY_MEMBER = 2
ASSASSINATION_GUARD_PER_LOCAL_LOYALIST = 3
ASSASSINATION_LEGITIMACY_WEIGHT = 0.25
RECOVERY_POLITYLESS_REPUTATION = 80
RECOVERY_POLITYLESS_PARTY_SIZE = 12
RECOVERY_CRISIS_REPUTATION = 60
RECOVERY_CRISIS_PARTY_SIZE = 8
RECOVERY_REGION_ORDER_STEP = 2
RECOVERY_REGION_CONTROL_STEP = 2
REGION_ACTIVITY_XP_STEP = 3
REGION_ACTIVITY_XP_REDUCTION = 0.05
REGION_ACTIVITY_XP_REDUCTION_CAP = 0.50

# ===========================================================================
# REFUGEES
# ===========================================================================
REFUGEE_COMMONER_THRESHOLD = 250
REFUGEE_ORDER_THRESHOLD = 60.0
REFUGEE_BASE_CHANCE = 0.12
REFUGEE_CRISIS_BONUS = 0.12
REFUGEE_LOW_BONUS = 0.06
REFUGEE_BATCH_MIN = 60
REFUGEE_BATCH_MAX = 180
REFUGEE_REGION_MIN = 1
REFUGEE_REGION_MAX = 3

# ===========================================================================
# DIPLOMACY / POLITICAL BLOCS
# ===========================================================================
DIPLOMACY_ENABLED = True
DIPLOMACY_CHECK_TICKS = TICKS_PER_MONTH * 3
DIPLOMACY_ALLIANCE_BASE_CHANCE = 0.10
DIPLOMACY_TRADE_BASE_CHANCE = 0.18
DIPLOMACY_ROYAL_MARRIAGE_BASE_CHANCE = 0.06
DIPLOMACY_MAX_ALLIES = 3
DIPLOMACY_MAX_TRADE_PARTNERS = 4
DIPLOMACY_ALLIANCE_STABILITY_BONUS = 2
DIPLOMACY_TRADE_STABILITY_BONUS = 1
DIPLOMACY_TRADE_ORDER_BONUS = 1
DIPLOMACY_TRUCE_TICKS = TICKS_PER_YEAR * 2

# ===========================================================================
# POLITY RELATIONSHIPS / RIVALRIES
# Persistent relationship memory drives major allies and major rivals.
# Scores are clamped from -100 (blood rival) to +100 (sworn ally).
# ===========================================================================
POLITY_RELATIONSHIPS_ENABLED = True
POLITY_RELATIONSHIP_MIN = -100
POLITY_RELATIONSHIP_MAX = 100
POLITY_MAJOR_RIVAL_THRESHOLD = -60
POLITY_MAJOR_ALLY_THRESHOLD = 60
POLITY_MAX_MAJOR_RIVALS = 2
POLITY_MAX_MAJOR_ALLIES = 2
POLITY_RELATIONSHIP_BORDER_FRICTION = -4
POLITY_RELATIONSHIP_COMPATIBILITY_WEIGHT = 1
POLITY_RELATIONSHIP_SHARED_RIVAL_BONUS = 8
POLITY_RELATIONSHIP_TRADE_BONUS = 6
POLITY_RELATIONSHIP_ALLIANCE_BONUS = 4
POLITY_RELATIONSHIP_MARRIAGE_BONUS = 12
POLITY_RELATIONSHIP_TRUCE_BONUS = 2
POLITY_RELATIONSHIP_HOSTILITY_PENALTY = -10
POLITY_RELATIONSHIP_HEGEMON_FEAR_PENALTY = -6
POLITY_RELATIONSHIP_CONQUEST_PENALTY = -35
POLITY_RELATIONSHIP_CLAIM_PRESSURE_PENALTY = -8
POLITY_RELATIONSHIP_TRADE_PACT_GAIN = 15
POLITY_RELATIONSHIP_ALLIANCE_GAIN = 30
POLITY_RELATIONSHIP_ROYAL_MARRIAGE_GAIN = 45
POLITY_RELATIONSHIP_RIVAL_COHESION_BONUS = 2
POLITY_RELATIONSHIP_ALLY_STABILITY_BONUS = 2
POLITY_RELATIONSHIP_DECAY_POSITIVE = 1
POLITY_RELATIONSHIP_DECAY_NEGATIVE = 0

# ===========================================================================
# PROSPERITY / ELITE CORRUPTION
# ===========================================================================
ELITE_CORRUPTION_ENABLED = True
ELITE_CORRUPTION_CHECK_TICKS = TICKS_PER_MONTH
ELITE_CORRUPTION_BASE_CHANCE = 0.035
ELITE_CORRUPTION_PROSPERITY_STOCKPILE_THRESHOLD = 150
ELITE_CORRUPTION_MIN_ORDER = 65
ELITE_CORRUPTION_MIN_REPUTATION = 40
ELITE_CORRUPTION_MAX_MONTHLY_ACTORS = 6
# Elites do not corrupt immediately on appointment. When an actor becomes a
# ruler/general/captain/lieutenant, they receive a private eligibility clock.
# If the run ends before that clock matures, they simply never rot. Good.
ELITE_CORRUPTION_OFFICE_WINDOW_MIN_YEARS = 3
ELITE_CORRUPTION_OFFICE_WINDOW_MAX_YEARS = 10
ELITE_CORRUPTION_OFFICE_WINDOW_DURATION_YEARS = 1
ELITE_CORRUPTION_MIN_CHARACTER_MULT = 0.03
ELITE_CORRUPTION_MAX_CHARACTER_MULT = 2.50
ELITE_CORRUPTION_DEITY_SHIFT_CHANCE = 0.35
ELITE_CORRUPTION_ALIGNMENT_SHIFT_CHANCE = 0.22

# ===========================================================================
# PARTIES
# ===========================================================================
LEADER_LONG_REST_MIN = 18
LEADER_LONG_REST_MAX = 54
PARTY_FOUNDING_PERCENTILE = 0.30
PARTY_FOUNDING_MIN_MEMBERS = 3
EVIL_PARTY_COUP_CHECK_TICKS = 30
EVIL_PARTY_COUP_BASE_CHANCE = 0.05
EVIL_PARTY_COUP_REP_MARGIN = 12
LEADER_XP_WEIGHT_MULTIPLIER = 1.75
XP_TO_REP_DIVISOR = 100
PARTY_SPLIT_SIZE_THRESHOLD = 100
PARTY_SPLIT_BASE_CHANCE = 0.03
PARTY_SPLIT_PER_MEMBER = 0.002

# ===========================================================================
# ECONOMY / RESOURCES
# ===========================================================================
ECONOMY_ENABLED = True
ECONOMY_TICK_INTERVAL = TICKS_PER_MONTH
ECONOMY_BASE_PRODUCTION_DIVISOR = 250
ECONOMY_GRAIN_REQUIRED_PER_COMMONERS = 500
ECONOMY_LOW_FOOD_ORDER_PENALTY = 2
ECONOMY_CRITICAL_FOOD_ORDER_PENALTY = 4

# =========================================================================
# CSV / METRICS EXPORT
# =========================================================================
# Fixed wide-schema slots. Do not generate metrics columns from entity names;
# dynamic gods/relics are written into these slots so long runs do not corrupt
# metrics.csv by changing row width mid-run.
CSV_RELIC_SLOTS = 24
ECONOMY_WOOD_REQUIRED_PER_COMMONERS = 1800
ECONOMY_METAL_REQUIRED_PER_COMMONERS = 4500
ECONOMY_WEAPONS_REQUIRED_PER_ADVENTURERS = 28
ECONOMY_ARMOR_REQUIRED_PER_ADVENTURERS = 35
ECONOMY_FOOD_RESERVE_MULTIPLIER = 2.0
ECONOMY_FOOD_ORDER_BONUS_RESERVE_MULTIPLIER = 2.0
ECONOMY_FOOD_SURPLUS_ORDER_BONUS = 1
ECONOMY_CRITICAL_FOOD_RATIO = 0.35
ECONOMY_STRATEGIC_RESERVE_MULTIPLIER = 1.5
ECONOMY_STRATEGIC_SHORTAGE_ORDER_PENALTY = 1
ECONOMY_INTERNAL_TRANSFER_CAP_PER_RESOURCE = 999999
ECONOMY_TRADE_TRANSFER_CAP_PER_RESOURCE = 80
ECONOMY_TRADE_RELATIONSHIP_IMPORT_BONUS = 2
ECONOMY_TRADE_DEPENDENCY_ALLY_BONUS = 4
ECONOMY_TRADE_SHORTAGE_RIVAL_PENALTY = -4
ECONOMY_TRADE_COMPETITION_PENALTY = -2

# ===========================================================================
# LORE: BARDIC MEMORY / SONG COMPOSITION
# Public songs feed myth/legend pressure. Private songs credit the bard, not the subject.
# ===========================================================================
LORE_TICK_INTERVAL = TICKS_PER_MONTH
LORE_MAX_BARDS_PER_TICK = 12
BARD_SONG_COOLDOWN_TICKS = TICKS_PER_MONTH
BARD_SONG_ACTION_CHANCE = 0.20
BARD_COMPOSE_NEW_SONG_CHANCE = 0.08
BARD_SONG_LOG_CHANCE = 0.10

# Category-first composition: a bard rolls one category, then only builds
# candidates for that category.  Equal weights are the intended "d9" default.
BARD_COMPOSITION_CATEGORY_WEIGHTS = {
    "love": 1.0,
    "folly": 1.0,
    "hymn": 1.0,
    "relic": 1.0,
    "terror": 1.0,
    "villain": 1.0,
    "withdrawn_friend": 1.0,
    "actor": 1.0,
    "mood": 1.0,
}

# Passive profiler for monthly lore spikes. Records timings only; does not
# change lore behavior. Summary can print the recent/slow stage records.
LORE_PROFILING_ENABLED = True
LORE_PROFILE_MAX_RECORDS = 36
LORE_PROFILE_SLOW_STAGE_SECONDS = 0.25
LORE_PROFILE_LOG_SLOW_STAGES = False

# ===========================================================================
# POLITY MILITARY / VETERAN SYSTEM
# ===========================================================================
MILITARY_GENERALS_PER_REGION = 1
MILITARY_CAPTAINS_PER_REGION = 2
MILITARY_LIEUTENANTS_PER_REGION = 4
MILITARY_ENLISTED_ACTORS_PER_100_LEVY = 2
MILITARY_NORMAL_MOBILIZATION_RATE = 0.30
MILITARY_CRISIS_MOBILIZATION_RATE = 0.60
MILITARY_MIN_LEVY_PER_REGION = 0
MILITARY_GENERAL_QUALITY_WEIGHT = 1.00
MILITARY_CAPTAIN_QUALITY_WEIGHT = 0.60
MILITARY_LIEUTENANT_QUALITY_WEIGHT = 0.35
MILITARY_ENLISTED_QUALITY_WEIGHT = 0.12
MILITARY_LEVY_QUALITY_WEIGHT = 0.015
MILITARY_QUALITY_CAPTURE_BONUS_DIVISOR = 90
MILITARY_QUALITY_CAPTURE_BONUS_MAX = 18
MILITARY_MAX_ENLISTED_PER_DIVISION = 30
MILITARY_COMMAND_COOLDOWN_TICKS = TICKS_PER_MONTH
WITHDRAWN_ACTORS_EXCLUDED_FROM_CRISES = True
BARD_ALLOW_MILITARY_OFFICE = False
BARD_ALLOW_MILITARY_ENLISTMENT = False
BARD_DUPLICATE_TITLE_BLOCK = True
BARD_COMPOSITION_FALLBACK_TO_PERFORMANCE = True
BARD_MIN_SUBJECT_SCORE = 14.0
BARD_PUBLIC_SUBJECT_MIN_SCORE = 32.0
BARD_PRIVATE_SUBJECT_MIN_SCORE = 16.0
BARD_PUBLIC_SUBJECT_MIN_REP = 18
BARD_PUBLIC_SUBJECT_MIN_LEVEL = 6
BARD_PUBLIC_SUBJECT_MIN_MONSTER_KILLS = 3
BARD_PUBLIC_SUBJECT_MIN_PARTY_SIZE = 8
BARD_PUBLIC_SUBJECT_MIN_MYTHIC_SCORE = 45.0
PRIVATE_SONG_PUBLIC_PERFORMANCES = 8
PRIVATE_SONG_PUBLIC_REGIONS = 3
PRIVATE_SONG_PUBLIC_POPULARITY = 25.0
PRIVATE_SONG_PUBLIC_HISTORICAL_WEIGHT = 18.0
PRIVATE_SONG_BARD_FAME_MULTIPLIER = 0.75
PRIVATE_SONG_BARD_REP_AWARD = 1
PRIVATE_SONG_BARD_CULTURAL_BONUS = 6.0
BARD_RECENT_SONG_WINDOW_YEARS = 20
BARD_SUBJECT_FATIGUE_FREE_SONGS = 3
BARD_SUBJECT_FATIGUE_STEP = 0.12
BARD_SUBJECT_FATIGUE_MIN_MULT = 0.35
TOP_SONG_CHART_COUNT = 10
SONG_POPULARITY_MONTHLY_DECAY = 0.965
SONG_HISTORICAL_WEIGHT_DECAY_FLOOR = 0.35
SONG_FORGET_POPULARITY_UNDER = 0.08

# Cultural songs are public culture but not myth/proto-cult fuel.
BARD_CULTURAL_COMPOSE_CHANCE = 0.16
BARD_LOVE_SONG_WEIGHT = 0.55
BARD_FOLLY_SONG_WEIGHT = 0.45
BARD_MENTAL_HAT_WEIGHT_EXPONENT = 0.70
BARD_WITHDRAWN_FRIEND_SONG_MIN_WEIGHT = 18.0
CULTURAL_SONG_PUBLIC_PERFORMANCES = 6
CULTURAL_SONG_PUBLIC_REGIONS = 2
CULTURAL_SONG_PUBLIC_POPULARITY = 18.0
CULTURAL_SONG_PUBLIC_HISTORICAL_WEIGHT = 14.0
CULTURAL_SONG_BARD_REP_AWARD = 1
CULTURAL_SONG_EFFECT_EVERY_PERFORMANCES = 5

# Love songs: cultural cohesion, legitimacy, and soft memory.
LOVE_SONG_MIN_COUPLE_SCORE = 55.0
LOVE_SONG_REGION_ORDER_BONUS = 1
LOVE_SONG_RULING_COUPLE_LEGITIMACY_BONUS = 1

# Folly songs: satire, cautionary memory, and legitimacy erosion.
FOLLY_SONG_MIN_REP = 20
FOLLY_SONG_BARD_REP_AWARD = 1
FOLLY_SONG_REGION_ORDER_BONUS = 0
FOLLY_SONG_RULER_LEGITIMACY_PENALTY = 1

# Rediscovery: bards can mine the morgue/tome for old material.
LORE_MORGUE_REDISCOVERY_ENABLED = True
LORE_MORGUE_MIN_DEAD_YEARS = 10
LORE_MORGUE_MAX_CANDIDATES = 24
LORE_MORGUE_MYTHIC_CANDIDATES = 60
LORE_TOME_REDISCOVERY_ENABLED = True
LORE_TOME_EVENT_SAMPLE_LIMIT = 40

# ===========================================================================
# LORE: PROTOCULT FORMATION / LEGEND PRESSURE
# ===========================================================================
PROTO_CULT_MIN_LEGEND_PRESSURE = 60.0
PROTO_CULT_MIN_DEAD_YEARS = 20
PROTO_CULT_MIN_MYTHIC_LEGACY = 220.0
PROTO_CULT_MIN_MYTHIC_AXES = 2
PROTO_CULT_MYTHIC_AXIS_FLOOR = 35.0
PROTO_CULT_PRESSURE_MEMORY_DECAY = 0.985
DEIFICATION_ENABLED = True
DEIFICATION_CHECK_INTERVAL_TICKS = TICKS_PER_YEAR
DEIFICATION_LEGEND_PRESSURE_THRESHOLD = 700.0
DEIFICATION_MIN_REGIONS = 2
DEIFICATION_BASE_CHANCE = 0.12
ASCENDED_GOD_STARTING_SOULS = 250
ASCENDED_COMMONER_MAX_LOCAL_CONVERT_RATE = 0.22

# ===========================================================================
# AI IMMORTAL ACTIONS
# ===========================================================================
AI_IMMORTAL_ACTIONS_ENABLED = True
AI_IMMORTAL_ACTION_INTERVAL_TICKS = TICKS_PER_SEASON
AI_IMMORTAL_MAX_GODS_PER_TICK = 2
AI_IMMORTAL_ACTION_COOLDOWN_TICKS = TICKS_PER_YEAR
AI_PROTO_CULT_SUPPRESS_SOUL_COST = 50
AI_PROTO_CULT_SUPPRESS_PRESSURE_MULT = 0.82
AI_HOLY_WARS_ENABLED = True
AI_HOLY_WAR_MIN_ATTACKER_INFLUENCE = 18.0
AI_HOLY_WAR_COOLDOWN_TICKS = 8640
AI_HOLY_WAR_CHANCE = 0.12

# ===========================================================================
# PLAYER-GOD INJECTION / EXISTING SAVES
# ===========================================================================
PLAYER_REVELATION_GRACE_YEARS = 8
PLAYER_REVELATION_SCHOOL_UNLOCK_INFLUENCE = 500
PLAYER_REVELATION_SCHOOL_UNLOCK_FOLLOWERS = 250
PLAYER_REVELATION_STARTING_SOULS = 0
PLAYER_CULT_ASCENSION_GRACE_YEARS = 3
PLAYER_CULT_ASCENSION_SCHOOL_UNLOCKED = True

# ===========================================================================
# WORLD-GENERATION TABLES
# ===========================================================================
# Expanded biome profiles.  These values are intentionally lightweight: they
# give regions flavor and soft pressure without turning terrain into a second
# rules engine.
BIOME_PROFILES = {
    "Farmland": {
        "capacity": (1800, 3600),
        "yields": {"grain": 1.90, "livestock": 1.25, "wood": 0.35, "metal": 0.10},
        "hardship": 15,
        "monster_pressure": 15,
        "settlement_appeal": 90,
        "adventure_appeal": 25,
        "description": "Rich cropland and dense settlements.",
    },
    "Plains": {
        "capacity": (1500, 3000),
        "yields": {"grain": 1.40, "livestock": 1.15, "wood": 0.45, "metal": 0.20},
        "hardship": 35,
        "monster_pressure": 25,
        "settlement_appeal": 70,
        "adventure_appeal": 35,
        "description": "Open grazing land and broad roads between towns.",
    },
    "Riverlands": {
        "capacity": (1700, 3400),
        "yields": {"grain": 1.65, "livestock": 1.00, "wood": 0.60, "metal": 0.25},
        "hardship": 20,
        "monster_pressure": 20,
        "settlement_appeal": 85,
        "adventure_appeal": 30,
        "description": "Fertile river valleys, mills, bridges, and trade crossings.",
    },
    "Forest": {
        "capacity": (1000, 2200),
        "yields": {"grain": 0.75, "livestock": 0.80, "wood": 1.45, "metal": 0.25},
        "hardship": 40,
        "monster_pressure": 45,
        "settlement_appeal": 55,
        "adventure_appeal": 55,
        "description": "Settled woodland with timber, hunting, and old roads.",
    },
    "Deep Forest": {
        "capacity": (700, 1700),
        "yields": {"grain": 0.50, "livestock": 0.65, "wood": 1.90, "metal": 0.20},
        "hardship": 65,
        "monster_pressure": 75,
        "settlement_appeal": 35,
        "adventure_appeal": 80,
        "description": "Ancient woods where few commoners travel willingly.",
    },
    "Highlands": {
        "capacity": (800, 1800),
        "yields": {"grain": 0.55, "livestock": 1.00, "wood": 0.60, "metal": 1.35},
        "hardship": 50,
        "monster_pressure": 50,
        "settlement_appeal": 45,
        "adventure_appeal": 60,
        "description": "Rugged hill country, sheep trails, and defensible ridges.",
    },
    "Mountains": {
        "capacity": (500, 1400),
        "yields": {"grain": 0.35, "livestock": 0.75, "wood": 0.45, "metal": 1.75},
        "hardship": 75,
        "monster_pressure": 70,
        "settlement_appeal": 25,
        "adventure_appeal": 85,
        "description": "Harsh mining country, stone passes, and hard borders.",
    },
    "Swamp": {
        "capacity": (500, 1500),
        "yields": {"grain": 0.45, "livestock": 0.45, "wood": 0.95, "metal": 0.15},
        "hardship": 70,
        "monster_pressure": 80,
        "settlement_appeal": 25,
        "adventure_appeal": 75,
        "description": "Waterlogged wilderness, strange lights, and stubborn villages.",
    },
    "Badlands": {
        "capacity": (350, 1200),
        "yields": {"grain": 0.35, "livestock": 0.60, "wood": 0.25, "metal": 0.85},
        "hardship": 85,
        "monster_pressure": 95,
        "settlement_appeal": 15,
        "adventure_appeal": 95,
        "description": "Broken frontier where ruins and monsters outnumber farms.",
    },
    "Desert": {
        "capacity": (250, 1100),
        "yields": {"grain": 0.25, "livestock": 0.55, "wood": 0.15, "metal": 0.70},
        "hardship": 90,
        "monster_pressure": 65,
        "settlement_appeal": 10,
        "adventure_appeal": 65,
        "description": "Dry roads, sparse wells, hard travel, and stubborn trade towns.",
    },
    "Tundra": {
        "capacity": (250, 1000),
        "yields": {"grain": 0.20, "livestock": 0.80, "wood": 0.35, "metal": 0.55},
        "hardship": 95,
        "monster_pressure": 75,
        "settlement_appeal": 10,
        "adventure_appeal": 70,
        "description": "Cold frontier scrubland where survival itself is work.",
    },
}

# Ordered cycling keeps small worlds varied without requiring terrain clustering yet.
BIOMES = [
    "Farmland", "Plains", "Riverlands", "Forest", "Deep Forest", "Highlands",
    "Mountains", "Swamp", "Badlands", "Desert", "Tundra",
]
TIME_OF_DAY = ["Morning", "Midday", "Evening", "Night"]
MONTH_NAMES = [
    "Dawnsreach", "Rainmoot", "Bloomtide", "Suncrest", "Goldfire", "Highsun",
    "Harvestwane", "Emberfall", "Duskmarch", "Frostburn", "Deepcold", "Yearsend",
]
REGION_PREFIXES = [
    "Green", "Stone", "Ash", "Wolf", "Oak", "Frost", "Gold", "Mist", "Black",
    "River", "Iron", "High", "Deep", "Red",
]
REGION_SUFFIXES = [
    "vale", "run", "mere", "watch", "field", "wood", "reach", "moor", "ford",
    "crest", "pass", "hollow", "heath", "fall",
]
TRAITS = [
    "brave", "cruel", "greedy", "patient", "zealous", "proud", "loyal", "cunning",
    "rash", "suspicious", "merciful", "vengeful", "stern", "curious", "brooding",
]
ROLE_WEIGHTS: List[Tuple[Role, int]] = [
    (Role.COMMONER, 80),
    (Role.FIGHTER, 10),
    (Role.WARDEN, 8),
    (Role.WIZARD, 2),
    (Role.BARD, 3),
]

# ===========================================================================
# NAME TABLES
# ===========================================================================
MALE_FIRST_NAMES = [
    "Alden", "Alfred", "Alric", "Andrew", "Ansel", "Arnold", "Arvid", "Ash", "Aster", "Auron",
    "Bain", "Bastian", "Beck", "Bennet", "Bram", "Branik", "Brian", "Bruce",
    "Cade", "Calder", "Cassian", "Cedric", "Corin",
    "Dain", "Darian", "Dav", "Derrik", "Dirk", "Donal", "Dorian", "Draven", "Drew",
    "Eamon", "Edgar", "Edric", "Eldric", "Ellis", "Eric", "Evander",
    "Falco", "Fenric", "Fenn", "Finnian", "Fraser",
    "Galen", "Garrik", "Gideon", "Godric", "Gregor",
    "Hadrian", "Hale", "Harlen", "Hector", "Henrik", "Hollowyn",
    "Icar", "Ilan", "Isen", "Ivan", "Iver", "Ivor",
    "Jarek", "Jarvis", "Jasper", "Jon", "Joran", "Jotham",
    "Kael", "Kellan", "Kelso", "Kiernan", "Korben",
    "Landon", "Lars", "Leif", "Loric", "Lucan", "Luther",
    "Malric", "Marek", "Mars", "Mathis", "Merkin", "Merrik", "Milo",
    "Nash", "Ned", "Neron", "Nestor", "Niall", "Norwin",
    "Oberon", "Olav", "Olli", "Oof", "Orion", "Orm", "Orrin", "Osric", "Osmond",
    "Paxton", "Perrin", "Pike", "Pix", "Porter",
    "Quaid", "Quentin", "Quill",
    "Rafferty", "Ragnar", "Riven", "Rob", "Robert", "Roderic", "Ronan", "Rook", "Rowan",
    "Silas", "Soren", "Stefan", "Stellan",
    "Tanner", "Taran", "Ted", "Thalamus", "Thane", "Theo", "Theron", "Thing",
    "Thomas", "Thor", "Tobin", "Tom", "Tommy", "Torin", "Trask", "Turd",
    "Ulric", "Urban", "Uther",
    "Vale", "Vance", "Varric", "Vigard", "Viggo",
    "Wesric", "Wilric", "Wolfhud", "Wren", "Wulfric", "Wyatt", "Wyn",
    "Xander",
    "Yestin", "Yorick",
    "Zachary", "Zane", "Zedric", "Zorin"
]
FEMALE_FIRST_NAMES = [
    "Adara", "Alina", "Amanda", "Anwen", "Aster", "Ayla",
    "Belwyn", "Bianca", "Briala", "Brenna", "Brina", "Brynn",
    "Cassia", "Celandine", "Celeste", "Clio", "Cora", "Coralie",
    "Danika", "Daphne", "Daria", "Delia", "Drusilla",
    "Edda", "Elara", "Elowen", "Ember", "Erin", "Eris", "Estra", "Evelyn",
    "Fable", "Faela", "Fenella", "Fiona", "Freya",
    "Garnet", "Gianna", "Giselle", "Greta", "Gwen",
    "Hadley", "Halea", "Hazaela", "Helena", "Hella", "Hestia", "Hildur", "Honora",
    "Ilena", "Ione", "Iris", "Isolde", "Ivana",
    "Jessamine", "Jessa", "Joriel", "Junia",
    "Kaida", "Kallia", "Kalista", "Kamila", "Kara", "Keira",
    "Lilith", "Lorelei", "Lunara", "Lyra", "Lysa",
    "Maren", "Mariel", "Melora", "Minerva", "Mira", "Moli",
    "Nadia", "Naomi", "Natalie", "Nerida", "Nessa", "Nina", "Noelle", "Nora", "Nova", "Nyla",
    "Odette", "Opaline", "Orla", "Oriana",
    "Pella", "Petra", "Portia", "Priscilla",
    "Qia", "Quinna", "Quendylon",
    "Ravena", "Rhea", "Riona", "Rosal", "Rowena",
    "Sabine", "Selene", "Sera", "Serafina", "Sylva",
    "Talia", "Tamsin", "Tarin", "Thea", "Theodora", "Thora", "Trista",
    "Ulani", "Uma", "Una", "Urielle", "Ursula",
    "Valea", "Velora", "Vera", "Verena", "Vesper",
    "Wanda", "Willa", "Willow", "Winna",
    "Xanthia", "Xaria", "Xenia", "Xochitl", "Xylia",
    "Yara", "Ysra", "Ysolde", "Yvette", "Yvon",
    "Zarela", "Zelda", "Zinnia", "Zora", "Zuri"
]
SURNAMES = [
    "Amber", "Ash",
    "Barrow", "Bastion", "Black", "Blackwell", "Bramble", "Briar", "Brightwood", "Brist",
    "Cask", "Cinder", "Clay", "Colt", "Conrad", "Cooper", "Craig", "Cross", "Crowe",
    "Dale", "Darkmoor", "Dawson", "Drake", "Dunn", "Dunley", "Dusk",
    "Eastmere", "Elden", "Ember", "Evercrest",
    "Fairchild", "Fallow", "Farrow", "Fen", "Fennel", "Fergusen", "Fett", "Flint", "Fox", "Frost",
    "Gage", "Gallow", "Glen", "Gold", "Granite", "Graves", "Green", "Gregersen", "Grove",
    "Hammer", "Hale", "Harrow", "Hart", "Hawke", "Hearth", "Hedstrom", "Highmere", "Hollow", "Hollis",
    "Inkwell", "Io", "Iron", "Ironside", "Irewood", "Ivory",
    "Jarrow", "Jasper", "Jett",
    "Keene", "Kestrel", "Kingsford", "Kingsley", "Knoll",
    "Langford", "Lark", "Lawrence", "Lawson", "Little", "Locke", "Lowell",
    "Marsh", "Mast", "Meadow", "Mercer", "Merrin", "Mills", "Mire", "Moon", "Morrow",
    "Nettle", "Noble", "North", "Norwood",
    "Oak", "Oaken", "Onyx", "Orchard", "Organa",
    "Peregrine", "Perkins", "Pike", "Pine", "Proudmore", "Pryce",
    "Quarry", "Queensley", "Quick", "Quickwater",
    "Raven", "Redfern", "Reed", "Ridge", "River", "Rook", "Rooker", "Roth", "Rowan",
    "Sable", "Schwarzenegger", "Silver", "Slate", "Stillwater", "Stone", "Stonebrook", "Storm", "Summer",
    "Tanner", "Thatch", "Thorne", "Thornfield", "Thorsson", "Timber", "Torr", "Trapps", "Turner",
    "Ulm", "Umber", "Umbral", "Underhill",
    "Vale", "Valewood", "Vane", "Verdant", "Voss", "Vossler",
    "Ward", "Westfall", "Whitlock", "Wick", "Windham", "Winter", "Wolf", "Wren",
    "Wythe",
    "Yardley", "Yarrow", "Yew", "Yorham",
    "Zale", "Zephyr", "Zorren"
]

# ===========================================================================
# LORE: REPERTOIRE / SONG TRANSMISSION / EXPANDED CULTURAL CATALOG
# ===========================================================================
BARD_REPERTOIRE_ENABLED = True
BARD_INITIAL_REPERTOIRE_MAX = 6
BARD_REPERTOIRE_MIN_SIZE = 12
BARD_REPERTOIRE_MAX_SIZE = 32
BARD_TOP_SONG_TARGET_MIN = 5
BARD_TOP_SONG_TARGET_MAX = 8
BARD_TOP_SONG_LEARN_CHANCE = 0.60
BARD_TOP_SONG_RANK_WEIGHT_FLATNESS = 0.65
BARD_REPERTOIRE_FILL_CHANCE = 0.45
BARD_REPERTOIRE_COMPOSE_FILL_CHANCE = 0.22
BARD_PERFORMANCE_CANDIDATE_POOL = 8
BARD_PERFORMANCE_SCORE_EXPONENT = 0.75
BARD_STALE_HIT_AGE_YEARS = 12
BARD_STALE_HIT_EXTRA_DECAY = 0.985
BARD_LEARN_REGIONAL_SONG_CHANCE = 0.22
BARD_LEARN_GLOBAL_SONG_CHANCE = 0.08
BARD_KNOWN_SONG_BONUS = 10.0
BARD_UNKNOWN_SONG_PENALTY = 0.55
BARD_UNIQUE_PERFORMER_WEIGHT = 1.25
BARD_REGION_SPREAD_WEIGHT = 1.4

# Civilizational mood songs: bard fame/culture only, no myth pipeline.
BARD_MOOD_COMPOSE_CHANCE = 0.12
BARD_EXISTENTIAL_SONG_WEIGHT = 0.30
BARD_PASTORAL_SONG_WEIGHT = 0.22
BARD_PROTEST_SONG_WEIGHT = 0.18
BARD_LAMENT_SONG_WEIGHT = 0.16
BARD_TAVERN_SONG_WEIGHT = 0.08
BARD_SEASONAL_SONG_WEIGHT = 0.06
MOOD_SONG_BARD_REP_AWARD = 1

# Villain songs: composed as warnings/trauma/protest, but can feed dark apotheosis.
BARD_VILLAIN_SONG_WEIGHT = 0.18
VILLAIN_SONG_MIN_SCORE = 80.0
VILLAIN_SONG_MIN_REP = 18
VILLAIN_SONG_KILL_WEIGHT = 1.8
VILLAIN_SONG_OPPRESSION_WEIGHT = 24.0
VILLAIN_SONG_AGE_WEIGHT = 0.6
VILLAIN_SONG_LEGEND_PRESSURE_MULT = 0.85

# Relic songs: hard-coded/world relics must be revealed before entering culture.
BARD_RELIC_SONG_WEIGHT = 0.16
RELIC_SONG_MIN_SCORE = 55.0
RELIC_SONG_FAILED_ATTEMPT_WEIGHT = 7.0
RELIC_SONG_DISCOVERY_WEIGHT = 2.0
RELIC_SONG_POSSESSION_EVENT_WEIGHT = 4.0
RELIC_SONG_AGE_ACTIVE_WEIGHT = 0.35
RELIC_LEGEND_PRESSURE_MULT = 0.65

# Monster songs and monster cults. Goblins are excluded from monster divinity.
BARD_MONSTER_SONG_WEIGHT = 0.16
MONSTER_SONG_MIN_SCORE = 90.0
MONSTER_SONG_MIN_KILLS = 25
MONSTER_SONG_MIN_AGE_YEARS = 12
MONSTER_SONG_KILL_WEIGHT = 2.0
MONSTER_SONG_COMMONER_KILL_WEIGHT = 0.03
MONSTER_SONG_AGE_WEIGHT = 1.0
MONSTER_SONG_REGION_WEIGHT = 12.0
MONSTER_SONG_ERADICATION_WEIGHT = 35.0
MONSTER_LEGEND_PRESSURE_MULT = 1.0
MONSTER_CULT_ENABLED = True
MONSTER_CULT_MIN_PRESSURE = 900.0
MONSTER_CULT_MIN_MYTHIC_LEGACY = 700.0
MONSTER_CULT_MIN_REGIONS = 3
MONSTER_CULT_MIN_AGE_YEARS = 35
MONSTER_CULT_MIN_KILLS = 100
MONSTER_CULT_MIN_ERADICATION_SURVIVALS = 3
MONSTER_CULT_COMMONER_FEAR_RATE = 0.015
MONSTER_CULT_ACTOR_AFFINITY_RATE = 0.010

# Organized eradication is narrower than ordinary monster combat.
MONSTER_ERADICATION_MIN_SIDE_POWER_RATIO = 0.75
MONSTER_ERADICATION_MIN_PARTY_SIZE = 6
MONSTER_ERADICATION_CHAMPION_BONUS = True
VETERAN_WITHDRAWAL_MONTHLY_CHANCE = 0.012
WITHDRAWAL_MIN_AGE = 35
