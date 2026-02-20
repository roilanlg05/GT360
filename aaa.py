from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple, Set


# ============================================================
# Helpers de tiempo (tu esquema: pick_up_date + HH:MM strings)
# ============================================================

def parse_yyyymmdd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))

def combine_date_time(pick_up_date: str, hhmm: str) -> datetime:
    d = parse_yyyymmdd(pick_up_date)
    t = parse_hhmm(hhmm)
    return datetime(d.year, d.month, d.day, t.hour, t.minute)

def to_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def minutes_between(a: datetime, b: datetime) -> int:
    return int(round((b - a).total_seconds() / 60))

def normalize_str(s: Optional[str]) -> str:
    return (s or "").strip().lower()


# ============================================================
# Modelo mínimo de Trip (ignora skip/limit/total/etc)
# ============================================================

@dataclass
class Trip:
    id: str
    location_id: str
    pick_up_date: str
    trip_type: str
    pick_up_location: str
    drop_off_location: str

    # horario "original real" (el pick_up_time del payload)
    original_input_time: datetime

    # bound superior (nunca puede quedar > original_bound_time)
    # si original_pick_up_time viene null -> bound = original_input_time
    original_bound_time: datetime

    # tiempo vigente (se va transformando filtro a filtro)
    current_time: datetime

    # Se usa en filtros que necesitan referencia al inicio del filtro
    base_time: Optional[datetime] = None

    # Pasajeros totales (riders["fligth"] + riders["in_fligth"])
    riders: int = 0

    # Resultado de asignación inteligente
    need_rescue: bool = False


def is_outbound(tr: Trip) -> bool:
    return normalize_str(tr.trip_type) == "outbound"

def is_inbound(tr: Trip) -> bool:
    return normalize_str(tr.trip_type) == "inbound"


# ============================================================
# Reglas de aplicación por rango (fecha/hora/hotel) + filtros
# ============================================================

@dataclass
class Rule:
    # Identificador opcional
    name: str = ""

    # Rango de fechas (inclusive). None = sin límite.
    date_from: Optional[str] = None  # "YYYY-MM-DD"
    date_to: Optional[str] = None    # "YYYY-MM-DD"

    # Rango de horas (diario) HH:MM. None = sin límite.
    time_from: Optional[str] = None  # "HH:MM"
    time_to: Optional[str] = None    # "HH:MM"

    # Hoteles (por pick_up_location). Vacío/None = todos.
    hotels: Optional[List[str]] = None

    # A qué filtros aplica esta regla (por defecto: a todos)
    # valores válidos: "reduce","expand","join","combine"
    filters: Optional[List[str]] = None

    # Overrides opcionales SOLO para reduce (para permitir ventanas con reduce distinto)
    reduce_minutes: Optional[int] = None


def rule_applies_to_filter(rule: Rule, filter_name: str) -> bool:
    if not rule.filters:
        return True
    fset = {normalize_str(x) for x in rule.filters}
    # alias: combine == join
    if filter_name == "join":
        return ("join" in fset) or ("combine" in fset)
    return normalize_str(filter_name) in fset


def trip_matches_rule(tr: Trip, rule: Rule, when_dt: datetime) -> bool:
    """
    when_dt: datetime de referencia para evaluar rango de hora (y fecha).
    Usamos el tiempo "vigente al inicio del filtro" (base_time).
    """
    # Fecha
    trip_day = when_dt.date()
    if rule.date_from:
        if trip_day < parse_yyyymmdd(rule.date_from):
            return False
    if rule.date_to:
        if trip_day > parse_yyyymmdd(rule.date_to):
            return False

    # Hora (diaria)
    if rule.time_from and rule.time_to:
        tf = parse_hhmm(rule.time_from)
        tt = parse_hhmm(rule.time_to)
        tcur = when_dt.time()

        # Rango normal (ej 09:00-10:00)
        if tf <= tt:
            if not (tf <= tcur <= tt):
                return False
        else:
            # Rango que cruza medianoche (ej 22:00-02:00)
            if not (tcur >= tf or tcur <= tt):
                return False
    elif rule.time_from or rule.time_to:
        raise ValueError("Si usas rango de hora debes pasar BOTH: time_from y time_to")

    # Hoteles
    if rule.hotels:
        hotels_norm = {normalize_str(h) for h in rule.hotels if normalize_str(h)}
        if hotels_norm and normalize_str(tr.pick_up_location) not in hotels_norm:
            return False

    return True


# ============================================================
# Config global de filtros (pipeline en cualquier orden)
# ============================================================

@dataclass
class FiltersConfig:
    # Orden exacto elegido por el usuario: puede ser 1, 2 o 3 filtros
    # acepta alias "combine" como sinónimo de "join"
    filters_order: List[str]

    # Reduce (default global)
    reduce_minutes: int = 0

    # Expand (discreto)
    min_gap_minutes: int = 30
    max_shift_minutes: int = 10
    shift_step_minutes: int = 5

    # Join/Combine
    join_window_minutes: int = 15
    join_respects_step: bool = True

    # Capacidad del vehículo
    van_capacity: int = 10            # pasajeros máximos por vehículo (0 = sin límite)

    # Distancias hotel-hotel y buffer de carga
    # hotel_distances: clave "hotel_a|hotel_b" -> minutos de trayecto
    # loading_buffer_minutes: tiempo mínimo de carga/descarga en hotel
    # Gap mínimo real entre trips de hoteles distintos =
    #   ceil((hotel_distance + loading_buffer) / 5) * 5
    hotel_distances: Optional[Dict[str, int]] = None
    loading_buffer_minutes: int = 5
    max_hotel_distance_minutes: int = 10  # (reservado para uso futuro / filtros externos)

    # Reglas (ventanas) para decidir qué trips pueden ser tocados por cada filtro
    rules: Optional[List[Rule]] = None


# ============================================================
# ✅ Config de asignación inteligente (rescue)
# ============================================================

@dataclass
class HotelTravel:
    # minutos hotel -> airport (cuando pick_up en hotel y drop_off airport)
    to_airport: int = 15
    # minutos airport -> hotel (cuando pick_up en airport y drop_off hotel)
    from_airport: int = 15

@dataclass
class RescueConfig:
    # Aeropuertos (por nombre exacto de location) ej ["SDF"]
    airport_codes: List[str]

    # Inbound uncertainty:
    flight_advance_max: int = 30  # 0..30 adelantado
    flight_delay_max: int = 30    # 0..30 atrasado
    crew_exit_min: int = 10       # 10..40 para salir
    crew_exit_max: int = 40

    # Buffers operacionales
    service_buffer_minutes: int = 0  # loading/unloading extra (si quieres)

    # Travel defaults
    default_travel_minutes: int = 15
    # Por hotel (key normalizada)
    hotel_travel_minutes: Dict[str, HotelTravel] = None
    # Overrides por par explícito "from|to" (keys normalizadas)
    pair_travel_minutes: Dict[str, int] = None

    # Búsqueda de foco (hotel principal)
    enable_focus_search: bool = True
    max_focus_candidates: int = 10  # limita hoteles a considerar (por densidad)

    def __post_init__(self) -> None:
        if self.hotel_travel_minutes is None:
            self.hotel_travel_minutes = {}
        if self.pair_travel_minutes is None:
            self.pair_travel_minutes = {}


def load_rescue_config_json(path: str) -> RescueConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    airports = raw.get("airport_codes") or ["SDF"]

    # hotel travel dict
    ht_raw = raw.get("hotel_travel_minutes") or {}
    ht: Dict[str, HotelTravel] = {}
    for k, v in ht_raw.items():
        nk = normalize_str(k)
        ht[nk] = HotelTravel(
            to_airport=int(v.get("to_airport", 15)),
            from_airport=int(v.get("from_airport", 15)),
        )

    # pair overrides
    pt_raw = raw.get("pair_travel_minutes") or {}
    pt: Dict[str, int] = {}
    for k, v in pt_raw.items():
        pt[normalize_str(k)] = int(v)

    return RescueConfig(
        airport_codes=[str(x) for x in airports],
        flight_advance_max=int(raw.get("flight_advance_max", 30)),
        flight_delay_max=int(raw.get("flight_delay_max", 30)),
        crew_exit_min=int(raw.get("crew_exit_min", 10)),
        crew_exit_max=int(raw.get("crew_exit_max", 40)),
        service_buffer_minutes=int(raw.get("service_buffer_minutes", 0)),
        default_travel_minutes=int(raw.get("default_travel_minutes", 15)),
        hotel_travel_minutes=ht,
        pair_travel_minutes=pt,
        enable_focus_search=bool(raw.get("enable_focus_search", True)),
        max_focus_candidates=int(raw.get("max_focus_candidates", 10)),
    )


def loc_key(s: str) -> str:
    return normalize_str(s)

def pair_key(a: str, b: str) -> str:
    return f"{loc_key(a)}|{loc_key(b)}"

def infer_airports_from_trips(trips: List[Trip], rcfg: RescueConfig) -> Set[str]:
    if rcfg.airport_codes:
        return {loc_key(x) for x in rcfg.airport_codes if loc_key(x)}
    airports = set()
    for t in trips:
        if is_inbound(t):
            airports.add(loc_key(t.pick_up_location))
        if is_outbound(t):
            airports.add(loc_key(t.drop_off_location))
    return airports

def travel_minutes(from_loc: Optional[str], to_loc: Optional[str], airports_norm: Set[str], rcfg: RescueConfig) -> int:
    if not from_loc or not to_loc:
        return 0
    a = loc_key(from_loc)
    b = loc_key(to_loc)
    if a == b:
        return 0

    pk = pair_key(a, b)
    if pk in rcfg.pair_travel_minutes:
        return int(rcfg.pair_travel_minutes[pk])

    a_is_airport = a in airports_norm
    b_is_airport = b in airports_norm

    if a_is_airport and not b_is_airport:
        ht = rcfg.hotel_travel_minutes.get(b)
        if ht:
            return int(ht.from_airport)
        return int(rcfg.default_travel_minutes)

    if not a_is_airport and b_is_airport:
        ht = rcfg.hotel_travel_minutes.get(a)
        if ht:
            return int(ht.to_airport)
        return int(rcfg.default_travel_minutes)

    if (not a_is_airport) and (not b_is_airport) and airports_norm:
        ap = next(iter(airports_norm))
        t1 = travel_minutes(a, ap, airports_norm, rcfg)
        t2 = travel_minutes(ap, b, airports_norm, rcfg)
        return int(t1 + t2)

    return int(rcfg.default_travel_minutes)


def inbound_window(tr: Trip, rcfg: RescueConfig) -> Tuple[datetime, datetime]:
    T = tr.current_time
    start = T - timedelta(minutes=int(rcfg.flight_advance_max)) + timedelta(minutes=int(rcfg.crew_exit_min))
    end = T + timedelta(minutes=int(rcfg.flight_delay_max) + int(rcfg.crew_exit_max))
    return start, end


def trip_required_start(tr: Trip, rcfg: RescueConfig) -> datetime:
    if is_outbound(tr):
        return tr.current_time
    if is_inbound(tr):
        s, _ = inbound_window(tr, rcfg)
        return s
    return tr.current_time


def trip_worst_end(tr: Trip, airports_norm: Set[str], rcfg: RescueConfig) -> Tuple[datetime, str]:
    if is_inbound(tr):
        _, wend = inbound_window(tr, rcfg)
        base_end = wend
    else:
        base_end = tr.current_time

    drive = travel_minutes(tr.pick_up_location, tr.drop_off_location, airports_norm, rcfg)
    end_dt = base_end + timedelta(minutes=int(drive) + int(rcfg.service_buffer_minutes))
    return end_dt, tr.drop_off_location


def can_follow(prev_end: datetime, prev_loc: str, nxt_start: datetime, nxt_pick: str, airports_norm: Set[str], rcfg: RescueConfig) -> bool:
    tmove = travel_minutes(prev_loc, nxt_pick, airports_norm, rcfg)
    return prev_end + timedelta(minutes=int(tmove)) <= nxt_start


def best_path_for_primary(
    trips: List[Trip],
    focus_loc_norm: Optional[str],
    airports_norm: Set[str],
    rcfg: RescueConfig
) -> Set[str]:
    if not trips:
        return set()

    nodes = []
    for t in trips:
        s = trip_required_start(t, rcfg)
        e, endloc = trip_worst_end(t, airports_norm, rcfg)
        nodes.append((t, s, e, endloc))

    nodes.sort(key=lambda x: (x[1], x[0].id))

    n = len(nodes)
    dp: List[Tuple[int, int]] = [(0, 0)] * n
    prev: List[int] = [-1] * n

    def is_focus(t: Trip) -> int:
        if not focus_loc_norm:
            return 0
        return 1 if loc_key(t.pick_up_location) == focus_loc_norm else 0

    for j in range(n):
        t_j, s_j, e_j, endloc_j = nodes[j]
        best_score = (1, is_focus(t_j))
        best_prev = -1

        for i in range(j):
            t_i, s_i, e_i, endloc_i = nodes[i]
            if can_follow(e_i, endloc_i, s_j, t_j.pick_up_location, airports_norm, rcfg):
                cand = (dp[i][0] + 1, dp[i][1] + is_focus(t_j))
                if cand > best_score:
                    best_score = cand
                    best_prev = i

        dp[j] = best_score
        prev[j] = best_prev

    end_idx = 0
    for j in range(n):
        if dp[j] > dp[end_idx]:
            end_idx = j

    chosen_ids: Set[str] = set()
    k = end_idx
    while k != -1:
        chosen_ids.add(nodes[k][0].id)
        k = prev[k]

    return chosen_ids


def greedy_assign_drivers_for_remaining(
    remaining: List[Trip],
    airports_norm: Set[str],
    rcfg: RescueConfig
) -> int:
    if not remaining:
        return 0

    items = []
    for t in remaining:
        s = trip_required_start(t, rcfg)
        e, endloc = trip_worst_end(t, airports_norm, rcfg)
        items.append((t, s, e, endloc))
    items.sort(key=lambda x: (x[1], x[0].id))

    drivers: List[Tuple[datetime, str]] = []

    for t, s, e, endloc in items:
        placed = False
        for idx in range(len(drivers)):
            avail_t, avail_loc = drivers[idx]
            if can_follow(avail_t, avail_loc, s, t.pick_up_location, airports_norm, rcfg):
                drivers[idx] = (e, endloc)
                placed = True
                break
        if not placed:
            drivers.append((e, endloc))

    return len(drivers)


def apply_intelligent_rescue_assignment(trips: List[Trip], rcfg: RescueConfig) -> None:
    by_loc: Dict[str, List[Trip]] = {}
    for t in trips:
        by_loc.setdefault(t.location_id or "default", []).append(t)

    for loc_id, loc_trips in by_loc.items():
        if not loc_trips:
            continue

        airports_norm = infer_airports_from_trips(loc_trips, rcfg)

        hotel_counts: Dict[str, int] = {}
        for t in loc_trips:
            pu = loc_key(t.pick_up_location)
            if pu and pu not in airports_norm:
                hotel_counts[pu] = hotel_counts.get(pu, 0) + 1

        focus_candidates: List[Optional[str]] = [None]
        if rcfg.enable_focus_search and hotel_counts:
            ranked = sorted(hotel_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ranked = ranked[: max(1, int(rcfg.max_focus_candidates))]
            focus_candidates += [k for k, _ in ranked]

        best_primary: Set[str] = set()
        best_total_drivers = 10**9
        best_primary_count = -1
        best_focus_hits = -1

        for focus in focus_candidates:
            primary_ids = best_path_for_primary(loc_trips, focus, airports_norm, rcfg)
            primary_count = len(primary_ids)

            remaining = [t for t in loc_trips if t.id not in primary_ids]
            drivers_extra = greedy_assign_drivers_for_remaining(remaining, airports_norm, rcfg)
            total_drivers = 1 + drivers_extra

            fh = 0
            if focus:
                for t in loc_trips:
                    if t.id in primary_ids and loc_key(t.pick_up_location) == focus:
                        fh += 1

            better = False
            if total_drivers < best_total_drivers:
                better = True
            elif total_drivers == best_total_drivers:
                if primary_count > best_primary_count:
                    better = True
                elif primary_count == best_primary_count:
                    if fh > best_focus_hits:
                        better = True

            if better:
                best_total_drivers = total_drivers
                best_primary_count = primary_count
                best_focus_hits = fh
                best_primary = primary_ids

        for t in loc_trips:
            t.need_rescue = (t.id not in best_primary)


# ============================================================
# Bounds / Validaciones básicas
# ============================================================

def clamp_candidate_time(tr: Trip, candidate: datetime) -> Optional[datetime]:
    if candidate > tr.original_bound_time:
        return None
    return candidate


def allowed_offsets(cfg: FiltersConfig) -> List[int]:
    step = max(1, int(cfg.shift_step_minutes))
    m = abs(int(cfg.max_shift_minutes))
    offsets = list(range(-m, m + 1, step))
    if 0 not in offsets:
        offsets.append(0)
    offsets.sort()
    return offsets


def is_eligible_for_filter(tr: Trip, cfg: FiltersConfig, filter_name: str) -> bool:
    # Join aplica a outbound Y a inbound (agrupar transfers desde aeropuerto)
    if filter_name == "join":
        if not (is_outbound(tr) or is_inbound(tr)):
            return False
        # Inbound: siempre elegible; su pickup es el aeropuerto, no un hotel
        if is_inbound(tr):
            return True
    elif not is_outbound(tr):
        return False

    rules = cfg.rules or []
    if not rules:
        return True

    base = tr.base_time or tr.current_time
    for r in rules:
        if rule_applies_to_filter(r, filter_name) and trip_matches_rule(tr, r, base):
            return True
    return False


def reduce_minutes_for_trip(tr: Trip, cfg: FiltersConfig) -> int:
    rules = cfg.rules or []
    if not rules:
        return cfg.reduce_minutes

    base = tr.base_time or tr.current_time
    for r in rules:
        if not rule_applies_to_filter(r, "reduce"):
            continue
        if trip_matches_rule(tr, r, base) and r.reduce_minutes is not None:
            return int(r.reduce_minutes)

    return cfg.reduce_minutes


# ============================================================
# Filtro: Reduce
# ============================================================

def apply_reduce(day_trips: List[Trip], cfg: FiltersConfig) -> None:
    for tr in day_trips:
        tr.base_time = tr.current_time

    for tr in day_trips:
        if not is_eligible_for_filter(tr, cfg, "reduce"):
            continue

        minutes = int(reduce_minutes_for_trip(tr, cfg))
        if minutes == 0:
            continue

        tr.current_time = tr.current_time - timedelta(minutes=minutes)
        if tr.current_time > tr.original_bound_time:
            tr.current_time = tr.original_bound_time

    for tr in day_trips:
        tr.base_time = None


# ============================================================
# Filtro: Expand (solo toca colisiones; shifts discretos; 0 permitido)
# ============================================================

def best_pair_adjustment(left: Trip, right: Trip, cfg: FiltersConfig) -> Tuple[datetime, datetime]:
    min_gap = effective_min_gap(left, right, cfg)
    offsets = allowed_offsets(cfg)

    lb = left.base_time if left.base_time else left.current_time
    rb = right.base_time if right.base_time else right.current_time

    left_can_move = is_eligible_for_filter(left, cfg, "expand")
    right_can_move = is_eligible_for_filter(right, cfg, "expand")

    left_cands: List[Tuple[int, datetime]] = []
    right_cands: List[Tuple[int, datetime]] = []

    if left_can_move:
        for o in offsets:
            cand = lb + timedelta(minutes=o)
            if abs(o) <= cfg.max_shift_minutes:
                cand2 = clamp_candidate_time(left, cand)
                if cand2 is not None:
                    left_cands.append((o, cand2))
    else:
        left_cands.append((0, left.current_time))

    if right_can_move:
        for o in offsets:
            cand = rb + timedelta(minutes=o)
            if abs(o) <= cfg.max_shift_minutes:
                cand2 = clamp_candidate_time(right, cand)
                if cand2 is not None:
                    right_cands.append((o, cand2))
    else:
        right_cands.append((0, right.current_time))

    best_score = None
    best_times = (left.current_time, right.current_time)

    for oL, tL in left_cands:
        for oR, tR in right_cands:
            gap = minutes_between(tL, tR)
            feasible = 1 if gap >= min_gap else 0
            sum_abs = abs(oL) + abs(oR)
            max_abs = max(abs(oL), abs(oR))
            score = (feasible, gap, -sum_abs, -max_abs)

            if best_score is None or score > best_score:
                best_score = score
                best_times = (tL, tR)

    return best_times


def apply_expand(day_trips: List[Trip], cfg: FiltersConfig) -> None:
    if not day_trips:
        return

    for tr in day_trips:
        tr.base_time = tr.current_time

    MAX_PASSES = 8
    for _ in range(MAX_PASSES):
        changed = False
        day_trips.sort(key=lambda x: (x.current_time, x.id))

        for i in range(len(day_trips) - 1):
            a = day_trips[i]
            b = day_trips[i + 1]
            gap = minutes_between(a.current_time, b.current_time)

            if gap >= effective_min_gap(a, b, cfg):
                continue

            new_a, new_b = best_pair_adjustment(a, b, cfg)
            if new_a != a.current_time or new_b != b.current_time:
                a.current_time = new_a
                b.current_time = new_b
                changed = True

        if not changed:
            break

    for tr in day_trips:
        tr.base_time = None


# ============================================================
# Filtro: Join/Combine (mejor “fit” dentro del rango) ✅
#   - Solo si mismo pick_up_location
#   - Gap <= join_window
#   - Escoge join_time dentro de [min..max] del cluster
#   - Optimiza gaps con vecino anterior/siguiente (balance)
# ============================================================

def minutes_since_day_start(dt: datetime) -> int:
    day0 = datetime(dt.year, dt.month, dt.day)
    return int(round((dt - day0).total_seconds() / 60))

def day_start(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)

def align_up(dt: datetime, step: int) -> datetime:
    m = minutes_since_day_start(dt)
    m2 = ((m + step - 1) // step) * step
    return day_start(dt) + timedelta(minutes=m2)

def align_down(dt: datetime, step: int) -> datetime:
    m = minutes_since_day_start(dt)
    m2 = (m // step) * step
    return day_start(dt) + timedelta(minutes=m2)

def is_step_aligned(base: datetime, target: datetime, step: int) -> bool:
    delta = minutes_between(base, target)
    return delta % step == 0

def join_time_valid(tr: Trip, join_time: datetime, cfg: FiltersConfig) -> bool:
    """
    Join solo mueve outbound elegible para 'join'.
    Si no es elegible => solo válido si join_time == current_time.
    """
    can_move = is_eligible_for_filter(tr, cfg, "join")
    if not can_move:
        return join_time == tr.current_time

    if join_time > tr.original_bound_time:
        return False

    if cfg.join_respects_step:
        step = max(1, int(cfg.shift_step_minutes))
        base = tr.base_time if tr.base_time else tr.current_time
        return is_step_aligned(base, join_time, step)

    return True

def same_pickup_location(a: Trip, b: Trip) -> bool:
    return normalize_str(a.pick_up_location) == normalize_str(b.pick_up_location)


def hotel_distance(a: str, b: str, cfg: FiltersConfig) -> int:
    """Minutos de viaje entre dos ubicaciones. 0 si son la misma, 10^9 si no se conoce el par."""
    na, nb = normalize_str(a), normalize_str(b)
    if na == nb:
        return 0
    if cfg.hotel_distances:
        pk = f"{na}|{nb}"
        pk_rev = f"{nb}|{na}"
        d = cfg.hotel_distances.get(pk) or cfg.hotel_distances.get(pk_rev)
        if d is not None:
            return int(d)
    return 10 ** 9  # par desconocido → no se puede hacer join


def can_join_location(a: Trip, b: Trip, cfg: FiltersConfig) -> bool:
    """
    Join requiere mismo pickup hotel Y mismo destino (ruta idéntica).

    Outbound: mismo pick_up_location (hotel) + mismo drop_off_location (aeropuerto).
    Inbound:  mismo pick_up_location (aeropuerto) + mismo drop_off_location (hotel).

    Trips de hoteles distintos NO se joinan — el driver necesita tiempo de traslado
    entre hoteles. Ese gap mínimo lo gestiona effective_min_gap() en el expand.
    """
    return (
        normalize_str(a.pick_up_location) == normalize_str(b.pick_up_location)
        and normalize_str(a.drop_off_location) == normalize_str(b.drop_off_location)
    )


def round_up_to_5(n: int) -> int:
    """Redondea n hacia arriba al múltiplo de 5 más cercano."""
    return ((n + 4) // 5) * 5


def effective_min_gap(a: Trip, b: Trip, cfg: FiltersConfig) -> int:
    """
    Gap mínimo requerido entre dos trips consecutivos.

    Misma ruta (mismo hotel + mismo destino):
        → 0 min (son joinables, pueden salir juntos)

    Hoteles distintos con distancia conocida:
        → ceil((distancia + loading_buffer) / 5) * 5
        Ejemplo: 3 min trayecto + 5 min carga = 8 → redondea a 10 min

    Par desconocido o tipos incompatibles:
        → cfg.min_gap_minutes  (fallback conservador)
    """
    # Misma ruta exacta → joinable, gap 0
    if (normalize_str(a.pick_up_location) == normalize_str(b.pick_up_location)
            and normalize_str(a.drop_off_location) == normalize_str(b.drop_off_location)):
        return 0

    # Determinar qué hoteles comparar según dirección del viaje
    if is_outbound(a) and is_outbound(b):
        dist = hotel_distance(a.pick_up_location, b.pick_up_location, cfg)
    elif is_inbound(a) and is_inbound(b):
        dist = hotel_distance(a.drop_off_location, b.drop_off_location, cfg)
    else:
        return cfg.min_gap_minutes  # mezcla outbound/inbound → no combinar

    if dist >= 10 ** 8:  # par desconocido
        return cfg.min_gap_minutes

    return round_up_to_5(dist + cfg.loading_buffer_minutes)


def cluster_fits_capacity(trips: List[Trip], cfg: FiltersConfig) -> bool:
    """True si el total de pasajeros del grupo cabe en el vehículo (0 = sin límite)."""
    if cfg.van_capacity <= 0:
        return True
    return sum(t.riders for t in trips) <= cfg.van_capacity


def find_best_capacity_subcluster(
    cluster: List[Trip],
    prev_trip: Optional[Trip],
    next_trip: Optional[Trip],
    cfg: FiltersConfig,
) -> Tuple[Optional[List[Trip]], Optional[datetime]]:
    """
    Dentro de un cluster que excede la capacidad, encuentra el sub-cluster contiguo
    de tamaño ≥ 2 que quepa en la van Y maximice la separación respecto a sus vecinos.

    Devuelve (sub_cluster, join_time). Si no existe ninguna combinación válida → (None, None).
    """
    n = len(cluster)
    best_sub: Optional[List[Trip]] = None
    best_jt: Optional[datetime] = None
    best_score: Optional[Tuple] = None

    for start in range(n):
        running_riders = 0
        for end in range(start, n):
            running_riders += cluster[end].riders
            if cfg.van_capacity > 0 and running_riders > cfg.van_capacity:
                break  # Añadir más trips desde este start no ayuda

            sub = cluster[start: end + 1]
            if len(sub) < 2:
                continue

            # Vecinos reales del sub-cluster dentro del cluster completo
            sub_prev = cluster[start - 1] if start > 0 else prev_trip
            sub_next = cluster[end + 1] if end + 1 < n else next_trip

            t_min = min(tr.current_time for tr in sub)
            t_max = max(tr.current_time for tr in sub)
            candidates = join_candidates_between(t_min, t_max, cfg)

            for jt in candidates:
                if not all(join_time_valid(tr, jt, cfg) for tr in sub):
                    continue
                sc = score_join_time(jt, sub, sub_prev, sub_next, cfg)
                if best_score is None or sc > best_score:
                    best_score = sc
                    best_jt = jt
                    best_sub = sub

    return best_sub, best_jt


def join_candidates_between(t_min: datetime, t_max: datetime, cfg: FiltersConfig) -> List[datetime]:
    if t_max < t_min:
        t_min, t_max = t_max, t_min

    # Siempre restrictivo: escoger dentro del rango [t_min..t_max]
    if t_min == t_max:
        return [t_min]

    if cfg.join_respects_step:
        step = max(1, int(cfg.shift_step_minutes))
        start = align_up(t_min, step)
        end = align_down(t_max, step)
        cands: List[datetime] = []
        cur = start
        while cur <= end:
            cands.append(cur)
            cur += timedelta(minutes=step)

        # fallback si por alguna razón no hay candidatos step-aligned
        if not cands:
            cands = [t_min, t_max]
        # asegúrate de incluir endpoints (por si ya están en ellos y pasan validación)
        if t_min not in cands:
            cands.append(t_min)
        if t_max not in cands:
            cands.append(t_max)
        cands = sorted(set(cands))
        return cands

    # sin step: cada minuto del rango
    span = max(0, minutes_between(t_min, t_max))
    return [t_min + timedelta(minutes=i) for i in range(span + 1)]

def score_join_time(
    jt: datetime,
    cluster: List[Trip],
    prev_trip: Optional[Trip],
    next_trip: Optional[Trip],
    cfg: FiltersConfig
) -> Tuple[int, int, int, int, int]:
    """
    Queremos que “caiga mejor”, o sea:
      1) si se puede, NO romper min_gap con vecinos (prev/next) -> feasible=1
      2) maximizar el MIN(gap_prev, gap_next) (balance)
      3) maximizar gap_prev + gap_next (espacio total)
      4) minimizar movimiento total
      5) minimizar el máximo movimiento
    """
    big = 10**9

    if prev_trip is not None:
        gap_prev = minutes_between(prev_trip.current_time, jt)
    else:
        gap_prev = big

    if next_trip is not None:
        gap_next = minutes_between(jt, next_trip.current_time)
    else:
        gap_next = big

    # feasible respecto al gap mínimo dinámico con cada vecino
    feasible = 1
    if prev_trip is not None and gap_prev < effective_min_gap(prev_trip, cluster[0], cfg):
        feasible = 0
    if next_trip is not None and gap_next < effective_min_gap(cluster[-1], next_trip, cfg):
        feasible = 0

    min_neighbor_gap = min(gap_prev, gap_next)
    sum_neighbor_gap = (0 if prev_trip is None else gap_prev) + (0 if next_trip is None else gap_next)

    # costo movimiento (desde base_time)
    moves: List[int] = []
    for tr in cluster:
        base = tr.base_time if tr.base_time else tr.current_time
        moves.append(abs(minutes_between(base, jt)))
    sum_abs = sum(moves)
    max_abs = max(moves) if moves else 0

    # Nota: sum_abs/max_abs los invertimos con signo negativo en el score
    return (feasible, min_neighbor_gap, sum_neighbor_gap, -sum_abs, -max_abs)

def apply_join(day_trips: List[Trip], cfg: FiltersConfig) -> None:
    if not day_trips:
        return

    # base_time al inicio del join
    for tr in day_trips:
        tr.base_time = tr.current_time

    day_trips.sort(key=lambda x: (x.current_time, x.id))

    i = 0
    while i < len(day_trips) - 1:
        a = day_trips[i]
        b = day_trips[i + 1]

        # Join: outbound+outbound o inbound+inbound con proximidad de hotel
        if not can_join_location(a, b, cfg):
            i += 1
            continue

        gap = minutes_between(a.current_time, b.current_time)
        if gap > cfg.join_window_minutes:
            i += 1
            continue

        # Construir cluster: consecutivos con ubicación compatible y gap <= join_window
        j = i + 1
        cluster = [a]
        while j < len(day_trips):
            prev = day_trips[j - 1]
            cur = day_trips[j]
            if not can_join_location(prev, cur, cfg):
                break
            if minutes_between(prev.current_time, cur.current_time) > cfg.join_window_minutes:
                break
            cluster.append(cur)
            j += 1

        start_idx = i
        end_idx = i + len(cluster) - 1

        if len(cluster) < 2:
            i += 1
            continue

        prev_trip = day_trips[start_idx - 1] if start_idx - 1 >= 0 else None
        next_trip = day_trips[end_idx + 1] if end_idx + 1 < len(day_trips) else None

        # ── Seleccionar sub-cluster según capacidad ───────────────────────────
        if cluster_fits_capacity(cluster, cfg):
            # Capacidad OK: operar sobre el cluster completo
            active_cluster = cluster
            ac_prev = prev_trip
            ac_next = next_trip

            t_min = min(tr.current_time for tr in active_cluster)
            t_max = max(tr.current_time for tr in active_cluster)
            candidates = join_candidates_between(t_min, t_max, cfg)

            best_jt: Optional[datetime] = None
            best_score: Optional[Tuple[int, int, int, int, int]] = None

            for jt in candidates:
                if not all(join_time_valid(tr, jt, cfg) for tr in active_cluster):
                    continue
                sc = score_join_time(jt, active_cluster, ac_prev, ac_next, cfg)
                if best_score is None or sc > best_score:
                    best_score = sc
                    best_jt = jt

            if best_jt is None:
                i += 1
                continue

        else:
            # Capacidad excedida: encontrar el mejor sub-cluster que quepa y maximice separación
            active_cluster, best_jt = find_best_capacity_subcluster(
                cluster, prev_trip, next_trip, cfg
            )
            if active_cluster is None or best_jt is None or len(active_cluster) < 2:
                i += 1
                continue

        # ── Anti-loop: si ya están todos en ese tiempo, avanzar ──────────────
        if all(tr.current_time == best_jt for tr in active_cluster):
            i = end_idx + 1
            continue

        # ── Aplicar join al sub-cluster activo ────────────────────────────────
        for tr in active_cluster:
            tr.current_time = best_jt

        # Reordenar y retroceder para capturar posibles merges adyacentes
        day_trips.sort(key=lambda x: (x.current_time, x.id))
        i = max(0, start_idx - 1)

    for tr in day_trips:
        tr.base_time = None


# ============================================================
# Pipeline por día (filtros opcionales en el orden elegido)
# ============================================================

def normalize_filter_name(name: str) -> str:
    n = normalize_str(name)
    if n == "combine":
        return "join"
    return n


def apply_filters_for_day(day_trips: List[Trip], cfg: FiltersConfig) -> None:
    for f in cfg.filters_order:
        f = normalize_filter_name(f)
        day_trips.sort(key=lambda x: (x.current_time, x.id))

        if f == "reduce":
            apply_reduce(day_trips, cfg)
        elif f == "expand":
            apply_expand(day_trips, cfg)
        elif f == "join":
            apply_join(day_trips, cfg)
        else:
            raise ValueError(f"Filtro desconocido: {f}")


# ============================================================
# Construcción desde tu payload (IGNORA skip/limit/total)
# ============================================================

def build_trips_from_payload(payload: Dict[str, Any]) -> List[Trip]:
    trips: List[Trip] = []
    for item in payload.get("data", []):
        pu_date = item["pick_up_date"]
        pu_time_str = item["pick_up_time"]
        pu_loc = item.get("pick_up_location") or ""
        do_loc = item.get("drop_off_location") or ""
        loc_id = str(item.get("location_id") or "default")

        original_input_dt = combine_date_time(pu_date, pu_time_str)

        bound_str = item.get("original_pick_up_time")
        if bound_str:
            bound_dt = combine_date_time(pu_date, bound_str)
        else:
            bound_dt = original_input_dt

        riders_raw = item.get("riders") or {}
        if isinstance(riders_raw, dict):
            riders = (
                int(riders_raw.get("fligth", 0) or 0)
                + int(riders_raw.get("in_fligth", 0) or 0)
            )
        else:
            riders = 0

        trips.append(
            Trip(
                id=str(item["id"]),
                location_id=loc_id,
                pick_up_date=pu_date,
                trip_type=item.get("trip_type", ""),
                pick_up_location=pu_loc,
                drop_off_location=do_loc,
                original_input_time=original_input_dt,
                original_bound_time=bound_dt,
                current_time=original_input_dt,
                riders=riders,
            )
        )
    return trips


def group_by_day(trips: List[Trip]) -> Dict[str, List[Trip]]:
    out: Dict[str, List[Trip]] = {}
    for tr in trips:
        out.setdefault(tr.pick_up_date, []).append(tr)
    return out


def build_output(trips_by_day: Dict[str, List[Trip]]) -> Dict[str, Any]:
    out_list: List[Dict[str, Any]] = []
    for d in sorted(trips_by_day.keys()):
        day = trips_by_day[d]
        day.sort(key=lambda x: (x.current_time, x.id))

        for idx, tr in enumerate(day):
            gap_next = None
            if idx < len(day) - 1:
                gap_next = minutes_between(tr.current_time, day[idx + 1].current_time)

            out_list.append(
                {
                    "id": tr.id,
                    "location_id": tr.location_id,
                    "pick_up_date": tr.pick_up_date,
                    "pick_up_location": tr.pick_up_location,
                    "original_pick_up_time": to_hhmm(tr.original_input_time),
                    "final_pick_up_time": to_hhmm(tr.current_time),
                    "gap_to_next_minutes": gap_next,
                    "needRescue": bool(tr.need_rescue),
                }
            )

    return {"data": out_list}


def process_payload(payload: Dict[str, Any], cfg: FiltersConfig, rescue_cfg: RescueConfig) -> Dict[str, Any]:
    trips = build_trips_from_payload(payload)
    by_day = group_by_day(trips)

    num_offsets = 2 * (abs(cfg.max_shift_minutes) // max(1, cfg.shift_step_minutes)) + 1
    print(
        f"[cfg] filters={cfg.filters_order} reduce={cfg.reduce_minutes} "
        f"min_gap={cfg.min_gap_minutes} max_shift={cfg.max_shift_minutes} "
        f"step={cfg.shift_step_minutes} join_window={cfg.join_window_minutes} "
        f"offsets={num_offsets} combos_per_pair~{num_offsets*num_offsets} "
        f"rules={len(cfg.rules or [])}"
    )

    for d, day_trips in by_day.items():
        print(f"[day] {d} trips={len(day_trips)}")
        apply_filters_for_day(day_trips, cfg)

    apply_intelligent_rescue_assignment(trips, rescue_cfg)

    return build_output(by_day)


# ============================================================
# CLI
# ============================================================

def parse_csv_list(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def load_rules_json(path: str) -> List[Rule]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "rules" in raw:
        raw_rules = raw["rules"]
    else:
        raw_rules = raw

    if not isinstance(raw_rules, list):
        raise ValueError("rules.json debe ser una lista o un dict con key 'rules': [ ... ]")

    rules: List[Rule] = []
    for r in raw_rules:
        rules.append(
            Rule(
                name=str(r.get("name", "")),
                date_from=r.get("date_from"),
                date_to=r.get("date_to"),
                time_from=r.get("time_from"),
                time_to=r.get("time_to"),
                hotels=r.get("hotels"),
                filters=r.get("filters"),
                reduce_minutes=r.get("reduce_minutes"),
            )
        )
    return rules


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trip pickup_time filter pipeline + intelligent rescue assignment")

    p.add_argument("--in", dest="in_path", required=True, help="Input JSON file (debe tener key 'data': [trips...])")
    p.add_argument("--out", dest="out_path", default="", help="Output JSON file; si no se pasa, imprime stdout")

    p.add_argument("--filters", required=True,
                   help="Orden de filtros separados por coma: reduce,expand,join (combine = alias de join)")

    # Config global
    p.add_argument("--reduce-minutes", type=int, default=0)
    p.add_argument("--min-gap", type=int, default=30)
    p.add_argument("--max-shift", type=int, default=10)
    p.add_argument("--step", type=int, default=5)
    p.add_argument("--join-window", type=int, default=15)
    p.add_argument("--join-respects-step", action="store_true",
                   help="Si se incluye, Join respeta el step discreto igual que Expand.")

    # Reglas
    p.add_argument("--rules-json", default="",
                   help="Path a JSON con múltiples reglas. Si se pasa, ignora flags de regla simple.")
    p.add_argument("--date-from", default="", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--date-to", default="", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--time-from", default="", help="HH:MM (inclusive)")
    p.add_argument("--time-to", default="", help="HH:MM (inclusive)")
    p.add_argument("--hotels", default="", help="CSV de pick_up_location exactos")
    p.add_argument("--rule-filters", default="",
                   help="CSV de filtros a los que aplica esta regla simple. Vacío=all.")
    p.add_argument("--rule-reduce-minutes", default="",
                   help="Override reduce para esta regla simple.")

    # Capacidad del vehículo y distancias entre hoteles
    p.add_argument("--van-capacity", type=int, default=10,
                   help="Pasajeros máximos por vehículo (0 = sin límite). Default: 10.")
    p.add_argument("--loading-buffer", type=int, default=5,
                   help="Minutos mínimos de carga/descarga en hotel. Se suma a la distancia "
                        "entre hoteles para calcular el gap mínimo entre trips. Default: 5.")
    p.add_argument("--max-hotel-distance", type=int, default=10,
                   help="Reservado (referencia externa). Default: 10.")
    p.add_argument("--hotel-distances-json", default="",
                   help="JSON con distancias hotel-hotel: {\"hotel_a|hotel_b\": minutos, ...}")

    # Rescue assignment config
    p.add_argument("--rescue-config-json", default="",
                   help="Path a JSON con configuración de travel times + inbound uncertainty + airports.")
    p.add_argument("--airports", default="SDF",
                   help="CSV airports fallback si no usas --rescue-config-json (default: SDF).")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    filters_order = [x.strip() for x in args.filters.split(",") if x.strip()]

    # Rules
    rules: List[Rule] = []
    if args.rules_json:
        rules = load_rules_json(args.rules_json)
    else:
        has_any_scope = any([
            args.date_from, args.date_to, args.time_from, args.time_to, args.hotels, args.rule_filters, args.rule_reduce_minutes
        ])
        if has_any_scope:
            rm_override = None
            if args.rule_reduce_minutes.strip():
                rm_override = int(args.rule_reduce_minutes)

            rf = parse_csv_list(args.rule_filters) if args.rule_filters.strip() else None
            hotels = parse_csv_list(args.hotels) if args.hotels.strip() else None

            rules = [
                Rule(
                    name="cli_rule",
                    date_from=args.date_from or None,
                    date_to=args.date_to or None,
                    time_from=args.time_from or None,
                    time_to=args.time_to or None,
                    hotels=hotels,
                    filters=rf,
                    reduce_minutes=rm_override,
                )
            ]

    hotel_distances_dict: Optional[Dict[str, int]] = None
    if args.hotel_distances_json:
        with open(args.hotel_distances_json, "r", encoding="utf-8") as f:
            raw_hd = json.load(f)
        hotel_distances_dict = {}
        for k, v in raw_hd.items():
            parts = k.split("|")
            if len(parts) == 2:
                nk = f"{normalize_str(parts[0])}|{normalize_str(parts[1])}"
                hotel_distances_dict[nk] = int(v)

    cfg = FiltersConfig(
        filters_order=filters_order,
        reduce_minutes=args.reduce_minutes,
        min_gap_minutes=args.min_gap,
        max_shift_minutes=args.max_shift,
        shift_step_minutes=args.step,
        join_window_minutes=args.join_window,
        join_respects_step=args.join_respects_step,
        van_capacity=args.van_capacity,
        loading_buffer_minutes=args.loading_buffer,
        max_hotel_distance_minutes=args.max_hotel_distance,
        hotel_distances=hotel_distances_dict,
        rules=rules or None,
    )

    if args.rescue_config_json:
        rescue_cfg = load_rescue_config_json(args.rescue_config_json)
    else:
        rescue_cfg = RescueConfig(
            airport_codes=parse_csv_list(args.airports) or ["SDF"],
        )

    out = process_payload(payload, cfg, rescue_cfg)

    if args.out_path:
        with open(args.out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    else:
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
