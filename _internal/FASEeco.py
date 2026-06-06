from __future__ import annotations

RESOURCE_TYPES = ("grain", "livestock", "wood", "metal", "weapons", "armor")
STRATEGIC_RESOURCES = ("wood", "metal", "weapons", "armor")

def _setting(sim, name, default):
    """Read economy settings from the simulator module/config first, then local fallback."""
    try:
        import sys
        module = sys.modules.get(sim.__class__.__module__)
        if module is not None and hasattr(module, name):
            return getattr(module, name)
    except Exception:
        pass
    return globals().get(name, default)

DEFAULT_YIELDS = {"grain": 0.90, "livestock": 0.80, "wood": 0.70, "metal": 0.45}

def _biome_profile(sim, biome: str) -> dict:
    profiles = _setting(sim, "BIOME_PROFILES", {}) or {}
    if not isinstance(profiles, dict):
        return {}
    key = str(biome or "")
    return profiles.get(key) or profiles.get(key.title()) or profiles.get(key.replace("_", " ").title()) or {}

def _biome_yields(sim, biome: str) -> dict:
    profile = _biome_profile(sim, biome)
    yields = profile.get("yields") if isinstance(profile, dict) else None
    return yields if isinstance(yields, dict) and yields else DEFAULT_YIELDS

def ensure_stockpile(region):
    stock = getattr(region, "stockpile", None)
    if not isinstance(stock, dict):
        stock = {}
    for resource in RESOURCE_TYPES:
        stock.setdefault(resource, 0)
    region.stockpile = stock
    return stock

def _empty_resource_map(value=0):
    return {resource: value for resource in RESOURCE_TYPES}

def ensure_economy_state(region):
    ensure_stockpile(region)
    for attr in ("economy_demand", "economy_surplus", "economy_deficit", "economy_imports", "economy_exports"):
        current = getattr(region, attr, None)
        if not isinstance(current, dict):
            current = {}
        for resource in RESOURCE_TYPES:
            current.setdefault(resource, 0)
        setattr(region, attr, current)
    if not hasattr(region, "economy_shortage_pressure"):
        region.economy_shortage_pressure = 0
    return region

def _living_adventurers_in_region(sim, region_id):
    world = getattr(sim, "world", None)
    if world is None:
        return 0
    try:
        actors = world.actors_in_region(region_id)
    except Exception:
        actors = []
    return sum(1 for a in actors if a.is_adventurer() and not getattr(a, "retired", False) and not getattr(a, "in_school", False))

def _region_demand(sim, region):
    world = sim.world
    pop = int(getattr(world, "commoners_by_region", {}).get(region.id, 0))
    adv = _living_adventurers_in_region(sim, region.id)
    grain_div = max(1, int(_setting(sim, "ECONOMY_GRAIN_REQUIRED_PER_COMMONERS", 500)))
    wood_div = max(1, int(_setting(sim, "ECONOMY_WOOD_REQUIRED_PER_COMMONERS", 1800)))
    metal_div = max(1, int(_setting(sim, "ECONOMY_METAL_REQUIRED_PER_COMMONERS", 4500)))
    arms_div = max(1, int(_setting(sim, "ECONOMY_WEAPONS_REQUIRED_PER_ADVENTURERS", 28)))
    armor_div = max(1, int(_setting(sim, "ECONOMY_ARMOR_REQUIRED_PER_ADVENTURERS", 35)))
    return {
        "grain": max(1, int(round(pop / grain_div))) if pop > 0 else 0,
        "livestock": 0,  # Livestock is a food buffer/resource, not direct monthly demand.
        "wood": max(0, int(round(pop / wood_div))),
        "metal": max(0, int(round(pop / metal_div))),
        "weapons": max(0, int(round(adv / arms_div))),
        "armor": max(0, int(round(adv / armor_div))),
    }

def _food_value(stock):
    return int(stock.get("grain", 0)) + int(stock.get("livestock", 0)) // 2

def _food_surplus(stock, demand):
    buffer_mult = float(_setting(_CURRENT_SIM, "ECONOMY_FOOD_RESERVE_MULTIPLIER", 2.0)) if _CURRENT_SIM is not None else 2.0
    reserve = int(round(max(0, demand) * buffer_mult))
    return max(0, int(stock.get("grain", 0)) - reserve)

def _resource_surplus(stock, resource, demand, reserve_mult):
    reserve = int(round(max(0, demand) * reserve_mult))
    return max(0, int(stock.get(resource, 0)) - reserve)

def _resource_deficit(stock, resource, demand):
    return max(0, int(demand) - int(stock.get(resource, 0)))

_CURRENT_SIM = None

def _move_resource(src_region, dst_region, resource, amount):
    if amount <= 0 or src_region is None or dst_region is None or src_region.id == dst_region.id:
        return 0
    src = ensure_stockpile(src_region)
    dst = ensure_stockpile(dst_region)
    amount = min(int(amount), int(src.get(resource, 0)))
    if amount <= 0:
        return 0
    src[resource] = int(src.get(resource, 0)) - amount
    dst[resource] = int(dst.get(resource, 0)) + amount
    ensure_economy_state(src_region).economy_exports[resource] += amount
    ensure_economy_state(dst_region).economy_imports[resource] += amount
    return amount

def _polity_regions(world, polity):
    return [world.regions[rid] for rid in getattr(polity, "region_ids", []) if rid in getattr(world, "regions", {})]

def _best_export_regions(regions, resource, reserve_mult):
    ranked = []
    for region in regions:
        stock = ensure_stockpile(region)
        demand = getattr(region, "economy_demand", {}) or {}
        if resource == "grain":
            surplus = _food_surplus(stock, int(demand.get("grain", 0)))
        else:
            surplus = _resource_surplus(stock, resource, int(demand.get(resource, 0)), reserve_mult)
        if surplus > 0:
            ranked.append((surplus, region))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked

def _deficit_regions(regions, resource):
    ranked = []
    for region in regions:
        stock = ensure_stockpile(region)
        demand = getattr(region, "economy_demand", {}) or {}
        if resource == "grain":
            deficit = max(0, int(demand.get("grain", 0)) - _food_value(stock))
        else:
            deficit = _resource_deficit(stock, resource, int(demand.get(resource, 0)))
        if deficit > 0:
            ranked.append((deficit, region))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked

def _redistribute_within_polity(sim, polity):
    world = sim.world
    regions = _polity_regions(world, polity)
    if len(regions) <= 1:
        return 0
    moved = 0
    reserve_mult = float(_setting(sim, "ECONOMY_STRATEGIC_RESERVE_MULTIPLIER", 1.5))
    transfer_cap = int(_setting(sim, "ECONOMY_INTERNAL_TRANSFER_CAP_PER_RESOURCE", 999999))
    for resource in ("grain",) + STRATEGIC_RESOURCES:
        remaining_cap = transfer_cap
        deficits = _deficit_regions(regions, resource)
        exporters = _best_export_regions(regions, resource, reserve_mult)
        if not deficits or not exporters:
            continue
        e_idx = 0
        for deficit, dst in deficits:
            need = deficit
            while need > 0 and remaining_cap > 0 and e_idx < len(exporters):
                surplus, src = exporters[e_idx]
                if surplus <= 0:
                    e_idx += 1
                    continue
                amount = min(need, surplus, remaining_cap)
                moved_now = _move_resource(src, dst, resource, amount)
                moved += moved_now
                need -= moved_now
                remaining_cap -= moved_now
                surplus -= moved_now
                exporters[e_idx] = (surplus, src)
                if moved_now <= 0 or surplus <= 0:
                    e_idx += 1
    return moved

def _polity_resource_totals(world, polity):
    totals = _empty_resource_map(0)
    demand = _empty_resource_map(0)
    for region in _polity_regions(world, polity):
        stock = ensure_stockpile(region)
        dem = getattr(region, "economy_demand", {}) or {}
        for resource in RESOURCE_TYPES:
            totals[resource] += int(stock.get(resource, 0))
            demand[resource] += int(dem.get(resource, 0))
    return totals, demand

def _polity_trade_supply(world, polity, resource, reserve_mult):
    supply = 0
    for region in _polity_regions(world, polity):
        stock = ensure_stockpile(region)
        demand = getattr(region, "economy_demand", {}) or {}
        if resource == "grain":
            supply += _food_surplus(stock, int(demand.get("grain", 0)))
        else:
            supply += _resource_surplus(stock, resource, int(demand.get(resource, 0)), reserve_mult)
    return max(0, int(supply))

def _polity_trade_need(world, polity, resource):
    need = 0
    for deficit, _region in _deficit_regions(_polity_regions(world, polity), resource):
        need += int(deficit)
    return max(0, need)

def _transfer_between_polities(sim, exporter, importer, resource, amount):
    world = sim.world
    reserve_mult = float(_setting(sim, "ECONOMY_STRATEGIC_RESERVE_MULTIPLIER", 1.5))
    exporters = _best_export_regions(_polity_regions(world, exporter), resource, reserve_mult)
    deficits = _deficit_regions(_polity_regions(world, importer), resource)
    moved = 0
    e_idx = 0
    for deficit, dst in deficits:
        need = min(deficit, amount - moved)
        while need > 0 and e_idx < len(exporters) and moved < amount:
            surplus, src = exporters[e_idx]
            if surplus <= 0:
                e_idx += 1
                continue
            take = min(need, surplus, amount - moved)
            moved_now = _move_resource(src, dst, resource, take)
            moved += moved_now
            need -= moved_now
            surplus -= moved_now
            exporters[e_idx] = (surplus, src)
            if moved_now <= 0 or surplus <= 0:
                e_idx += 1
        if moved >= amount:
            break
    if moved > 0:
        _ensure_polity_economy_state(exporter)
        _ensure_polity_economy_state(importer)
        exporter.trade_exports[resource] = exporter.trade_exports.get(resource, 0) + moved
        importer.trade_imports[resource] = importer.trade_imports.get(resource, 0) + moved
        exporter.economic_trade_partners[importer.id] = exporter.economic_trade_partners.get(importer.id, 0) + moved
        importer.economic_trade_partners[exporter.id] = importer.economic_trade_partners.get(exporter.id, 0) + moved
    return moved

def _ensure_polity_economy_state(polity):
    for attr in ("economic_stockpile", "economic_demand", "economic_surplus", "economic_deficit", "trade_imports", "trade_exports"):
        current = getattr(polity, attr, None)
        if not isinstance(current, dict):
            current = {}
        for resource in RESOURCE_TYPES:
            current.setdefault(resource, 0)
        setattr(polity, attr, current)
    if not isinstance(getattr(polity, "economic_trade_partners", None), dict):
        polity.economic_trade_partners = {}
    if not hasattr(polity, "trade_dependency_score"):
        polity.trade_dependency_score = 0
    if not hasattr(polity, "shortage_pressure"):
        polity.shortage_pressure = 0

def _settle_polity_trade(sim):
    world = sim.world
    if not getattr(world, "polities", None):
        return
    reserve_mult = float(_setting(sim, "ECONOMY_STRATEGIC_RESERVE_MULTIPLIER", 1.5))
    trade_cap = int(_setting(sim, "ECONOMY_TRADE_TRANSFER_CAP_PER_RESOURCE", 80))
    for polity in world.polities.values():
        _ensure_polity_economy_state(polity)
        polity.trade_imports = _empty_resource_map(0)
        polity.trade_exports = _empty_resource_map(0)
        polity.economic_trade_partners = {}
    # Internal redistribution first.
    for polity in world.polities.values():
        _redistribute_within_polity(sim, polity)
    # External trade pact exchange.
    for importer in list(world.polities.values()):
        partners = [world.polities.get(pid) for pid in getattr(importer, "trade_partner_ids", []) if pid in world.polities]
        partners = [p for p in partners if p is not None and p.id != importer.id]
        if not partners:
            continue
        for resource in ("grain",) + STRATEGIC_RESOURCES:
            need = _polity_trade_need(world, importer, resource)
            if need <= 0:
                continue
            remaining = min(need, trade_cap)
            exporters = []
            for exporter in partners:
                supply = _polity_trade_supply(world, exporter, resource, reserve_mult)
                if supply > 0:
                    exporters.append((supply, exporter))
            exporters.sort(key=lambda item: item[0], reverse=True)
            for supply, exporter in exporters:
                if remaining <= 0:
                    break
                moved = _transfer_between_polities(sim, exporter, importer, resource, min(remaining, supply))
                remaining -= moved

def _consume_and_apply_shortages(sim):
    world = sim.world
    strategic_penalty_step = max(1, int(_setting(sim, "ECONOMY_STRATEGIC_SHORTAGE_ORDER_PENALTY", 1)))
    low_food_penalty = int(_setting(sim, "ECONOMY_LOW_FOOD_ORDER_PENALTY", 2))
    critical_food_penalty = int(_setting(sim, "ECONOMY_CRITICAL_FOOD_ORDER_PENALTY", 4))
    for region in world.regions.values():
        ensure_economy_state(region)
        stock = ensure_stockpile(region)
        demand = getattr(region, "economy_demand", {}) or _empty_resource_map(0)
        deficit = _empty_resource_map(0)
        surplus = _empty_resource_map(0)

        # Food consumption: grain first, livestock as emergency food at 2:1.
        grain_need = int(demand.get("grain", 0))
        available_food = _food_value(stock)
        if available_food >= grain_need:
            grain_used = min(int(stock.get("grain", 0)), grain_need)
            stock["grain"] -= grain_used
            remaining = grain_need - grain_used
            if remaining > 0:
                stock["livestock"] = max(0, int(stock.get("livestock", 0)) - remaining * 2)
            if grain_need > 0 and int(stock.get("grain", 0)) > grain_need * float(_setting(sim, "ECONOMY_FOOD_ORDER_BONUS_RESERVE_MULTIPLIER", 2.0)) and getattr(region, "order", 0) < 90:
                region.order = min(100, int(getattr(region, "order", 0)) + int(_setting(sim, "ECONOMY_FOOD_SURPLUS_ORDER_BONUS", 1)))
        else:
            ratio = available_food / max(1, grain_need)
            penalty = critical_food_penalty if ratio < float(_setting(sim, "ECONOMY_CRITICAL_FOOD_RATIO", 0.35)) else low_food_penalty
            region.order = max(0, int(getattr(region, "order", 0)) - penalty)
            deficit["grain"] = grain_need - available_food
            stock["grain"] = 0
            stock["livestock"] = 0

        # Strategic upkeep/consumption. Deficits are political/economic pressure, not direct deaths.
        strategic_pressure = 0
        for resource in STRATEGIC_RESOURCES:
            need = int(demand.get(resource, 0))
            if need <= 0:
                surplus[resource] = max(0, int(stock.get(resource, 0)))
                continue
            used = min(int(stock.get(resource, 0)), need)
            stock[resource] = int(stock.get(resource, 0)) - used
            if used < need:
                deficit[resource] = need - used
                strategic_pressure += deficit[resource]
            surplus[resource] = max(0, int(stock.get(resource, 0)) - need)

        if strategic_pressure > 0:
            region.order = max(0, int(getattr(region, "order", 0)) - min(3, strategic_penalty_step + strategic_pressure // 8))

        # Material conversion happens after upkeep.
        weapon_batches = int(stock.get("metal", 0)) // 12
        if weapon_batches > 0:
            stock["metal"] -= weapon_batches * 12
            stock["weapons"] += weapon_batches
        armor_batches = min(int(stock.get("metal", 0)) // 8, int(stock.get("wood", 0)) // 4)
        if armor_batches > 0:
            stock["metal"] -= armor_batches * 8
            stock["wood"] -= armor_batches * 4
            stock["armor"] += armor_batches

        # Refresh visible snapshots after consumption/conversion.
        for resource in RESOURCE_TYPES:
            if resource == "grain":
                surplus[resource] = _food_surplus(stock, grain_need)
                if deficit[resource] <= 0:
                    deficit[resource] = max(0, grain_need - _food_value(stock))
            else:
                if deficit[resource] <= 0:
                    deficit[resource] = _resource_deficit(stock, resource, int(demand.get(resource, 0)))
                surplus[resource] = max(0, int(stock.get(resource, 0)) - int(demand.get(resource, 0)))
        region.economy_deficit = deficit
        region.economy_surplus = surplus
        region.economy_shortage_pressure = int(deficit.get("grain", 0)) * 3 + sum(int(deficit.get(r, 0)) for r in STRATEGIC_RESOURCES)

def _refresh_polity_economy_snapshots(sim):
    world = sim.world
    for polity in getattr(world, "polities", {}).values():
        _ensure_polity_economy_state(polity)
        totals, demand = _polity_resource_totals(world, polity)
        surplus = _empty_resource_map(0)
        deficit = _empty_resource_map(0)
        shortage_pressure = 0
        for region in _polity_regions(world, polity):
            r_sur = getattr(region, "economy_surplus", {}) or {}
            r_def = getattr(region, "economy_deficit", {}) or {}
            for resource in RESOURCE_TYPES:
                surplus[resource] += int(r_sur.get(resource, 0))
                deficit[resource] += int(r_def.get(resource, 0))
        shortage_pressure = int(deficit.get("grain", 0)) * 3 + sum(int(deficit.get(r, 0)) for r in STRATEGIC_RESOURCES)
        polity.economic_stockpile = totals
        polity.economic_demand = demand
        polity.economic_surplus = surplus
        polity.economic_deficit = deficit
        polity.shortage_pressure = shortage_pressure
        imports_total = sum(int(v) for v in getattr(polity, "trade_imports", {}).values())
        demand_total = max(1, sum(int(v) for v in demand.values()))
        polity.trade_dependency_score = int(round(100 * imports_total / demand_total))

def settle_world_economy(sim):
    """Finish the monthly economy pass after all regions have produced.

    This phase creates actual supply/demand behavior:
    1. redistributes within polities,
    2. moves resources through trade pacts,
    3. applies shortages/order pressure,
    4. stores region/polity economic snapshots for politics and summaries.
    """
    global _CURRENT_SIM
    _CURRENT_SIM = sim
    world = sim.world
    for region in world.regions.values():
        ensure_economy_state(region)
    _settle_polity_trade(sim)
    _consume_and_apply_shortages(sim)
    _refresh_polity_economy_snapshots(sim)
    _CURRENT_SIM = None

def region_economy_tick(sim, region):
    if not bool(_setting(sim, "ECONOMY_ENABLED", True)):
        return
    world = sim.world
    # Reset once per monthly economy pass, even tho the caller still invokes us per-region.
    marker = int(getattr(world, "tick", 0))
    if getattr(world, "_economy_pass_tick", None) != marker:
        world._economy_pass_tick = marker
        world._economy_regions_processed = set()
        world.economy_trade_volume = 0
        for reg in world.regions.values():
            ensure_economy_state(reg)
            reg.economy_demand = _empty_resource_map(0)
            reg.economy_surplus = _empty_resource_map(0)
            reg.economy_deficit = _empty_resource_map(0)
            reg.economy_imports = _empty_resource_map(0)
            reg.economy_exports = _empty_resource_map(0)
            reg.economy_shortage_pressure = 0

    ensure_economy_state(region)
    stock = ensure_stockpile(region)
    pop = int(getattr(world, "commoners_by_region", {}).get(region.id, 0))
    if pop > 0:
        order_ratio = max(0.05, min(1.25, float(getattr(region, "order", 50)) / 100.0))
        biome = str(getattr(region, "biome", ""))
        yields = _biome_yields(sim, biome)
        divisor = max(1, int(_setting(sim, "ECONOMY_BASE_PRODUCTION_DIVISOR", 250)))
        base = max(1, int((pop * order_ratio) / divisor))
        for resource, mod in yields.items():
            stock[resource] += max(0, int(round(base * mod)))
    region.economy_demand = _region_demand(sim, region)

    processed = getattr(world, "_economy_regions_processed", set())
    processed.add(region.id)
    world._economy_regions_processed = processed
    if len(processed) >= len(getattr(world, "regions", {}) or {}):
        settle_world_economy(sim)
