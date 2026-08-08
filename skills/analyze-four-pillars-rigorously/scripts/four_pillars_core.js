#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { TextDecoder } = require('util');

const ENGINE_VERSION = '0.1.0';
const RESPONSE_SCHEMA = 'xuanshu-four-pillars-core-response-v0.2';
const DATA_SCHEMA = 'xuanshu-calendar-data-v0.2';
const DATA_PATH = path.join(__dirname, 'data', 'calendar-1901-2033.json');
const EXPECTED_DATA_SHA256 = '65189952013b9471e6a0e8a63109ce6305d6242588ec6e3fabdb8ddd0bdd4509';
const MAX_INPUT_BYTES = 4 * 1024 * 1024;
const MAX_OUTPUT_BYTES = 32 * 1024 * 1024;
const DAY_MS = 86400000;
const BEIJING_OFFSET_MS = 8 * 3600000;

const STEMS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸'];
const BRANCHES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
const ELEMENTS = ['木', '火', '土', '金', '水'];
const STEM_ELEMENTS = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4];
const BRANCH_ELEMENTS = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4];
const ELEMENT_GENERATES = [1, 2, 3, 4, 0];
const ELEMENT_CONTROLS = [2, 3, 4, 0, 1];
const TERRAIN_NAMES = ['长生', '沐浴', '冠带', '临官', '帝旺', '衰', '病', '死', '墓', '绝', '胎', '养'];
const TERRAIN_START = [11, 6, 2, 9, 2, 9, 5, 0, 8, 3];
const NAYIN = [
  '海中金', '炉中火', '大林木', '路旁土', '剑锋金', '山头火',
  '涧下水', '城头土', '白蜡金', '杨柳木', '泉中水', '屋上土',
  '霹雳火', '松柏木', '长流水', '沙中金', '山下火', '平地木',
  '壁上土', '金箔金', '覆灯火', '天河水', '大驿土', '钗钏金',
  '桑柘木', '大溪水', '沙中土', '天上火', '石榴木', '大海水',
];
const HIDDEN_STEMS = [
  [[9, 'main']],
  [[5, 'main'], [9, 'middle'], [7, 'residual']],
  [[0, 'main'], [2, 'middle'], [4, 'residual']],
  [[1, 'main']],
  [[4, 'main'], [1, 'middle'], [9, 'residual']],
  [[2, 'main'], [6, 'middle'], [4, 'residual']],
  [[3, 'main'], [5, 'middle']],
  [[5, 'main'], [3, 'middle'], [1, 'residual']],
  [[6, 'main'], [8, 'middle'], [4, 'residual']],
  [[7, 'main']],
  [[4, 'main'], [7, 'middle'], [3, 'residual']],
  [[8, 'main'], [0, 'middle']],
];
const LUNAR_MONTH_NAMES = ['正月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'];
const LUNAR_DAY_NAMES = [
  '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
  '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
  '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十',
];

let calendarCache = null;

class CoreError extends Error {
  constructor(kind, code, message) {
    super(message);
    this.name = 'CoreError';
    this.kind = kind;
    this.code = code;
  }
}

function inputError(code, message) {
  throw new CoreError('input', code, message);
}

function assertAllowedKeys(value, allowed, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    inputError('INVALID_CORE_REQUEST', `${label} must be an object`);
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) inputError('INVALID_CORE_REQUEST', `Unknown ${label} field: ${key}`);
  }
}

function runtimeError(message) {
  throw new CoreError('runtime', 'INTERNAL_CORE_ERROR', message);
}

function modulo(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function sha256Bytes(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function decodeUtf8(buffer, label) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch (_error) {
    inputError('INVALID_UTF8', `${label} is not strict UTF-8`);
  }
}

function strictJson(buffer, label) {
  const text = decodeUtf8(buffer, label);
  try {
    return JSON.parse(text);
  } catch (_error) {
    inputError('INVALID_JSON', `${label} is not valid JSON`);
  }
}

function assertRuntime(condition, message) {
  if (!condition) runtimeError(message);
}

function loadCalendar() {
  if (calendarCache !== null) return calendarCache;
  let bytes;
  let coreBytes;
  try {
    bytes = fs.readFileSync(DATA_PATH);
    coreBytes = fs.readFileSync(__filename);
  } catch (error) {
    runtimeError(`Required core artifact could not be read: ${error.message}`);
  }
  let data;
  try {
    data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch (error) {
    runtimeError(`Calendar dataset is not strict UTF-8 JSON: ${error.message}`);
  }
  const dataSha256 = sha256Bytes(bytes);
  assertRuntime(dataSha256 === EXPECTED_DATA_SHA256, 'Calendar dataset SHA-256 mismatch');
  assertRuntime(data && data.schema_version === DATA_SCHEMA, 'Calendar dataset schema mismatch');
  assertRuntime(data.calendar_core_version === 'jpl-de440s-skyfield-1.54-v1', 'Calendar core identity mismatch');
  const coverage = data.coverage || {};
  assertRuntime(coverage.supported_gregorian_year_min === 1901, 'Calendar minimum coverage mismatch');
  assertRuntime(coverage.supported_gregorian_year_max === 2033, 'Calendar maximum coverage mismatch');
  assertRuntime(coverage.lunar_year_padding_min === 1900, 'Calendar left padding is missing');
  assertRuntime(coverage.public_solar_start === '1901-01-01', 'Public solar start mismatch');
  assertRuntime(coverage.public_solar_end === '2033-12-31', 'Public solar end mismatch');
  assertRuntime(coverage.lunar_label_year_envelope_min === 1900, 'Lunar label minimum mismatch');
  assertRuntime(coverage.lunar_label_year_envelope_max === 2033, 'Lunar label maximum mismatch');
  assertRuntime(coverage.context_events_from === '1900-01-01', 'Calendar term left context is missing');
  assertRuntime(String(coverage.context_events_through || '') >= '2034-01-31', 'Calendar right context is missing');
  assertRuntime(Array.isArray(data.terms) && data.terms.length > 3200, 'Calendar term table is incomplete');
  assertRuntime(Array.isArray(data.lunar_months) && data.lunar_months.length > 1600, 'Calendar lunar table is incomplete');
  assertRuntime(Array.isArray(data.lunar_uncertainty_events), 'Calendar uncertainty table is missing');
  const sourceNames = data.encoding && data.encoding.delta_t_source_codes;
  assertRuntime(sourceNames && Object.keys(sourceNames).length === 4, 'Delta-T source-code map is missing');

  const terms = data.terms.map((row) => {
    assertRuntime(Array.isArray(row) && row.length === 4, 'Invalid term row');
    const [milliseconds, index, guardSeconds, sourceCode] = row;
    assertRuntime(Number.isInteger(milliseconds), 'Term time is not an integer millisecond');
    assertRuntime(Number.isInteger(index) && index >= 0 && index < 24, 'Invalid term index');
    assertRuntime(Number.isInteger(guardSeconds) && guardSeconds >= 0, 'Invalid term model guard');
    assertRuntime(sourceNames[String(sourceCode)] !== undefined, 'Invalid term Delta-T source code');
    return { milliseconds, index, guardSeconds, sourceCode };
  });
  for (let i = 1; i < terms.length; i += 1) {
    assertRuntime(terms[i].milliseconds > terms[i - 1].milliseconds, 'Term rows are not strictly sorted');
  }
  const termNames = data.encoding.term_names_by_index;
  assertRuntime(Array.isArray(termNames) && termNames.length === 24, 'Term names are incomplete');

  const months = data.lunar_months.map((row) => {
    assertRuntime(Array.isArray(row) && row.length === 10, 'Invalid lunar-month row');
    const [startDay, lunarYear, month, leap, length, startMilliseconds, marginMilliseconds,
      startGuardSeconds, sourceCode, flags] = row;
    assertRuntime(Number.isInteger(startDay), 'Invalid lunar month start');
    assertRuntime(Number.isInteger(lunarYear) && lunarYear >= 1900 && lunarYear <= 2034, 'Invalid lunar year');
    assertRuntime(Number.isInteger(month) && month >= 1 && month <= 12, 'Invalid lunar month');
    assertRuntime(leap === 0 || leap === 1, 'Invalid lunar leap flag');
    assertRuntime(length === 29 || length === 30, 'Invalid lunar month length');
    assertRuntime(Number.isInteger(startMilliseconds), 'Invalid lunar new-moon time');
    assertRuntime(Number.isInteger(marginMilliseconds) && marginMilliseconds >= 0, 'Invalid lunar midnight margin');
    assertRuntime(Number.isInteger(startGuardSeconds) && startGuardSeconds >= 0, 'Invalid lunar model guard');
    assertRuntime(sourceNames[String(sourceCode)] !== undefined, 'Invalid lunar Delta-T source code');
    assertRuntime(Number.isInteger(flags) && flags >= 0, 'Invalid lunar uncertainty flags');
    return {
      startDay, lunarYear, month, leap: Boolean(leap), length, startMilliseconds,
      marginMilliseconds, startGuardSeconds, sourceCode, flags,
    };
  });
  for (let i = 1; i < months.length; i += 1) {
    assertRuntime(months[i].startDay === months[i - 1].startDay + months[i - 1].length,
      'Lunar month rows are not contiguous');
  }
  const day1901 = Math.floor(Date.UTC(1901, 0, 1) / DAY_MS);
  const day2034 = Math.floor(Date.UTC(2034, 0, 1) / DAY_MS);
  assertRuntime(months[0].startDay <= day1901, 'Lunar left context does not cover 1901-01-01');
  assertRuntime(months.at(-1).startDay + months.at(-1).length > day2034,
    'Lunar right context does not cover 2034-01-01');
  assertRuntime(months.some((row) => row.lunarYear === 1900), 'Lunar year 1900 padding is absent');
  assertRuntime(terms.some((row) => row.index === 21 && row.milliseconds < Date.UTC(1901, 0, 1)),
    'Lichun 1900 context is absent');
  assertRuntime(terms.some((row) => row.milliseconds > Date.UTC(2034, 0, 1)),
    'Next-term context after 2033 is absent');
  const firstPublic = months[findLastAtOrBefore(months, day1901, (row) => row.startDay)];
  const lastPublicDay = Math.floor(Date.UTC(2033, 11, 31) / DAY_MS);
  const lastPublic = months[findLastAtOrBefore(months, lastPublicDay, (row) => row.startDay)];
  assertRuntime(firstPublic.lunarYear === 1900 && firstPublic.month === 11 && !firstPublic.leap &&
    day1901 - firstPublic.startDay + 1 === 11, 'First public lunar label sentinel mismatch');
  assertRuntime(lastPublic.lunarYear === 2033 && lastPublic.month === 11 && lastPublic.leap &&
    lastPublicDay - lastPublic.startDay + 1 === 10, 'Last public lunar label sentinel mismatch');

  const uncertaintyByStartDay = new Map();
  for (const row of data.lunar_uncertainty_events) {
    assertRuntime(Array.isArray(row) && row.length === 9, 'Invalid lunar uncertainty event');
    const [monthStartDay, eventType, milliseconds, termIndex, marginMilliseconds,
      guardSeconds, sourceCode, changesAssignment, alternativeDayDelta] = row;
    assertRuntime(Number.isInteger(monthStartDay), 'Invalid uncertainty month key');
    assertRuntime(Number.isInteger(eventType) && eventType >= 0 && eventType <= 3,
      'Invalid uncertainty event type');
    assertRuntime(Number.isInteger(milliseconds), 'Invalid uncertainty event time');
    assertRuntime(Number.isInteger(termIndex) && termIndex >= -1 && termIndex < 24,
      'Invalid uncertainty term index');
    assertRuntime(Number.isInteger(marginMilliseconds) && marginMilliseconds >= 0,
      'Invalid uncertainty margin');
    assertRuntime(Number.isInteger(guardSeconds) && guardSeconds >= 0,
      'Invalid uncertainty model guard');
    assertRuntime(sourceNames[String(sourceCode)] !== undefined, 'Invalid uncertainty source code');
    assertRuntime(changesAssignment === 0 || changesAssignment === 1,
      'Invalid uncertainty assignment flag');
    assertRuntime([-1, 0, 1].includes(alternativeDayDelta), 'Invalid uncertainty day delta');
    const event = {
      eventType, milliseconds, termIndex, marginMilliseconds, guardSeconds,
      sourceCode, changesAssignment: Boolean(changesAssignment), alternativeDayDelta,
    };
    if (!uncertaintyByStartDay.has(monthStartDay)) uncertaintyByStartDay.set(monthStartDay, []);
    uncertaintyByStartDay.get(monthStartDay).push(event);
  }

  calendarCache = {
    data,
    dataSha256,
    nodeCoreSha256: sha256Bytes(coreBytes),
    terms,
    termNames,
    months,
    uncertaintyByStartDay,
    sourceNames,
  };
  return calendarCache;
}

function pad(value, width = 2) {
  return String(value).padStart(width, '0');
}

function parseIso(value, options = {}) {
  const { requireZ = false, label = 'datetime' } = options;
  if (typeof value !== 'string') inputError('INVALID_CORE_REQUEST', `${label} must be a string`);
  const expression = requireZ
    ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$/
    : /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/;
  const match = value.match(expression);
  if (!match) inputError('INVALID_CORE_REQUEST', `Invalid ${label}: ${value}`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = match[6] === undefined ? 0 : Number(match[6]);
  const microsecond = Number(String(match[7] || '').padEnd(6, '0') || '0');
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) {
    inputError('INVALID_CORE_REQUEST', `Out-of-range ${label}: ${value}`);
  }
  const milliseconds = Date.UTC(year, month - 1, day, hour, minute, second);
  const check = new Date(milliseconds);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 ||
      check.getUTCDate() !== day || check.getUTCHours() !== hour ||
      check.getUTCMinutes() !== minute || check.getUTCSeconds() !== second) {
    inputError('INVALID_CORE_REQUEST', `Nonexistent ${label}: ${value}`);
  }
  const epochMicroseconds = milliseconds * 1000 + microsecond;
  return { value, year, month, day, hour, minute, second, microsecond, milliseconds, epochMicroseconds };
}

function parseTimeOnly(value) {
  const match = String(value).match(/^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/);
  if (!match) inputError('INVALID_CORE_REQUEST', `Invalid time: ${value}`);
  const parsed = parseIso(`2000-01-01T${value}`, { label: 'time' });
  return parsed;
}

function localIso(parts) {
  const base = `${pad(parts.year, 4)}-${pad(parts.month)}-${pad(parts.day)}T` +
    `${pad(parts.hour)}:${pad(parts.minute)}:${pad(parts.second)}`;
  if (!parts.microsecond) return base;
  return `${base}.${pad(parts.microsecond, 6)}`;
}

function utcIsoFromMilliseconds(milliseconds) {
  return new Date(milliseconds).toISOString();
}

function beijingIsoFromMilliseconds(milliseconds) {
  return new Date(milliseconds + BEIJING_OFFSET_MS).toISOString().replace(/Z$/, '');
}

function unixDayFromParts(parts) {
  return Math.floor(Date.UTC(parts.year, parts.month - 1, parts.day) / DAY_MS);
}

function partsFromUnixDay(day) {
  const date = new Date(day * DAY_MS);
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
}

function findLastAtOrBefore(rows, value, selector) {
  let low = 0;
  let high = rows.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (selector(rows[middle]) <= value) low = middle + 1;
    else high = middle;
  }
  return low - 1;
}

function findMonthByDay(day) {
  const calendar = loadCalendar();
  const index = findLastAtOrBefore(calendar.months, day, (row) => row.startDay);
  if (index < 0 || day >= calendar.months[index].startDay + calendar.months[index].length) {
    inputError('UNSUPPORTED_CALENDAR_RANGE', 'The Beijing calendar day is outside the frozen dataset');
  }
  return { row: calendar.months[index], index };
}

function ganzhi(index) {
  const normalized = modulo(index, 60);
  return {
    index: normalized,
    stemIndex: normalized % 10,
    branchIndex: normalized % 12,
    name: `${STEMS[normalized % 10]}${BRANCHES[normalized % 12]}`,
  };
}

function ganzhiIndexFromStemBranch(stemIndex, branchIndex) {
  for (let index = 0; index < 60; index += 1) {
    if (index % 10 === stemIndex && index % 12 === branchIndex) return index;
  }
  runtimeError('Incompatible stem and branch parity');
}

function yearGanzhi(year) {
  return ganzhi(year - 1984);
}

function dayGanzhi(unixDay, dayBoundary, hour) {
  let adjustedDay = unixDay;
  if (dayBoundary === 'zi_initial_next_day' && hour === 23) adjustedDay += 1;
  return ganzhi(adjustedDay - Math.floor(Date.UTC(2000, 0, 7) / DAY_MS));
}

function tenGod(dayStemIndex, targetStemIndex) {
  const dayElement = STEM_ELEMENTS[dayStemIndex];
  const targetElement = STEM_ELEMENTS[targetStemIndex];
  const samePolarity = dayStemIndex % 2 === targetStemIndex % 2;
  if (dayElement === targetElement) return samePolarity ? '比肩' : '劫财';
  if (ELEMENT_GENERATES[dayElement] === targetElement) return samePolarity ? '食神' : '伤官';
  if (ELEMENT_GENERATES[targetElement] === dayElement) return samePolarity ? '偏印' : '正印';
  if (ELEMENT_CONTROLS[dayElement] === targetElement) return samePolarity ? '偏财' : '正财';
  if (ELEMENT_CONTROLS[targetElement] === dayElement) return samePolarity ? '七杀' : '正官';
  runtimeError('Invalid Five-Element relationship');
}

function terrain(dayStemIndex, branchIndex) {
  const start = TERRAIN_START[dayStemIndex];
  const phase = dayStemIndex % 2 === 0
    ? modulo(branchIndex - start, 12)
    : modulo(start - branchIndex, 12);
  return TERRAIN_NAMES[phase];
}

function pillarData(position, pillar, dayStemIndex) {
  const stemIndex = pillar.stemIndex;
  const branchIndex = pillar.branchIndex;
  return {
    position,
    ganzhi: pillar.name,
    ganzhi_evidence_layer: 'L1B_VERSIONED_CALENDAR',
    attribute_evidence_layer: 'L1C_VERSIONED_TRADITIONAL_MAP',
    stem: {
      name: STEMS[stemIndex],
      element: ELEMENTS[STEM_ELEMENTS[stemIndex]],
      yin_yang: stemIndex % 2 === 0 ? 'yang' : 'yin',
      ten_god: position === 'day' ? '日主' : tenGod(dayStemIndex, stemIndex),
    },
    branch: {
      name: BRANCHES[branchIndex],
      element: ELEMENTS[BRANCH_ELEMENTS[branchIndex]],
      yin_yang: branchIndex % 2 === 0 ? 'yang' : 'yin',
      hidden_stems: HIDDEN_STEMS[branchIndex].map(([hiddenStemIndex, role]) => ({
        name: STEMS[hiddenStemIndex],
        role,
        ten_god: tenGod(dayStemIndex, hiddenStemIndex),
      })),
    },
    terrain: terrain(dayStemIndex, branchIndex),
    nayin: NAYIN[Math.floor(pillar.index / 2)],
  };
}

function termData(term) {
  const calendar = loadCalendar();
  const beijingTime = beijingIsoFromMilliseconds(term.milliseconds);
  const divergence = (calendar.data.validation_facts.solar_term_date_divergences || []).find(
    (fact) => fact.term === calendar.termNames[term.index] &&
      fact.computed_beijing_date === beijingTime.slice(0, 10)
  ) || null;
  return {
    name: calendar.termNames[term.index],
    kind: term.index % 2 === 1 ? 'jie' : 'qi',
    beijing_time: beijingTime,
    utc: utcIsoFromMilliseconds(term.milliseconds),
    time_scale: 'TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY',
    model_guard_seconds: term.guardSeconds,
    delta_t_source_code: calendar.sourceNames[String(term.sourceCode)],
    historical_oracle_date_divergence: divergence,
  };
}

function termContext(absoluteMicroseconds) {
  const calendar = loadCalendar();
  const index = findLastAtOrBefore(
    calendar.terms,
    absoluteMicroseconds,
    (term) => term.milliseconds * 1000
  );
  if (index < 0 || index + 1 >= calendar.terms.length) {
    inputError('UNSUPPORTED_CALENDAR_RANGE', 'Solar-term context is outside the frozen dataset');
  }
  return { current: calendar.terms[index], next: calendar.terms[index + 1], index };
}

function latestTermMatching(absoluteMicroseconds, predicate) {
  const calendar = loadCalendar();
  let index = findLastAtOrBefore(
    calendar.terms,
    absoluteMicroseconds,
    (term) => term.milliseconds * 1000
  );
  while (index >= 0 && !predicate(calendar.terms[index])) index -= 1;
  if (index < 0) inputError('UNSUPPORTED_CALENDAR_RANGE', 'Required prior solar term is unavailable');
  return { term: calendar.terms[index], index };
}

function nextTermMatching(afterIndex, predicate) {
  const calendar = loadCalendar();
  for (let index = afterIndex + 1; index < calendar.terms.length; index += 1) {
    if (predicate(calendar.terms[index])) return { term: calendar.terms[index], index };
  }
  inputError('UNSUPPORTED_CALENDAR_RANGE', 'Required next solar term is unavailable');
}

function calendarModelBoundaryTerms(absoluteMicroseconds) {
  const calendar = loadCalendar();
  return calendar.terms.filter((term) =>
    term.index % 2 === 1 &&
    Math.abs(absoluteMicroseconds - term.milliseconds * 1000) <=
      term.guardSeconds * 1000000
  );
}

function calendarModelVariantData(boundary, state) {
  return {
    variant_id: `${boundary.milliseconds}:${state}`,
    state,
    classification_rule: state === 'birth_before_term'
      ? 'year_and_month_classified_immediately_before_the_guarded_Jie'
      : 'year_and_month_classified_immediately_after_the_guarded_Jie',
    boundary_term: termData(boundary),
  };
}

function solarTermBoundaryUncertainty(boundary, absoluteMicroseconds, state = null) {
  if (boundary === null) {
    return {
      status: 'CLEAR',
      codes: [],
      affects_year_pillar: false,
      affects_month_pillar: false,
      unresolved_result_change_without_enumerated_variant: false,
      per_event_model_guard_is_certified_error_bound: false,
      enumerated_variant_count: 1,
      calendar_model_variant_state: null,
      events: [],
    };
  }
  return {
    status: 'ENUMERATED_CALENDAR_MODEL_VARIANTS',
    codes: ['SOLAR_TERM_BOUNDARY_MODEL_GUARD'],
    affects_year_pillar: boundary.index === 21,
    affects_month_pillar: true,
    unresolved_result_change_without_enumerated_variant: false,
    per_event_model_guard_is_certified_error_bound: false,
    enumerated_variant_count: 2,
    calendar_model_variant_state: state,
    events: [{
      ...termData(boundary),
      absolute_distance_seconds:
        Math.abs(absoluteMicroseconds - boundary.milliseconds * 1000) / 1000000,
      changes_calendar_assignment: true,
    }],
  };
}

function absolutePillars(absoluteMicroseconds) {
  const lichun = latestTermMatching(absoluteMicroseconds, (term) => term.index === 21).term;
  const lichunBeijing = new Date(lichun.milliseconds + BEIJING_OFFSET_MS);
  const solarYear = lichunBeijing.getUTCFullYear();
  const yearPillar = yearGanzhi(solarYear);
  const jie = latestTermMatching(absoluteMicroseconds, (term) => term.index % 2 === 1).term;
  const monthOffset = modulo(jie.index - 21, 24) / 2;
  assertRuntime(Number.isInteger(monthOffset), 'Invalid Jie sequence for month pillar');
  const monthStem = modulo((yearPillar.stemIndex % 5) * 2 + 2 + monthOffset, 10);
  const monthBranch = modulo(2 + monthOffset, 12);
  return {
    year: yearPillar,
    month: ganzhi(ganzhiIndexFromStemBranch(monthStem, monthBranch)),
  };
}

function localDayHourPillars(parts, dayBoundary) {
  if (!['zi_initial_next_day', 'late_zi_same_day'].includes(dayBoundary)) {
    inputError('INVALID_CORE_REQUEST', `Unsupported day_boundary: ${dayBoundary}`);
  }
  const civilDay = unixDayFromParts(parts);
  const day = dayGanzhi(civilDay, dayBoundary, parts.hour);
  const hourBranch = Math.floor((parts.hour + 1) / 2) % 12;
  const hourStemBasis = parts.hour === 23
    ? ganzhi(civilDay + 1 - Math.floor(Date.UTC(2000, 0, 7) / DAY_MS)).stemIndex
    : day.stemIndex;
  const hourStem = modulo((hourStemBasis % 5) * 2 + hourBranch, 10);
  return { day, hour: ganzhi(ganzhiIndexFromStemBranch(hourStem, hourBranch)) };
}

function ziPolicyData(rule) {
  if (rule === 'zi_initial_next_day') {
    return {
      provider: 'xuanshu.IndependentZiInitialNextDay',
      zi_day_rollover: '23:00_begins_next_day_pillar',
      zi_hour_stem_basis: 'day_pillar_after_23:00_rollover',
    };
  }
  return {
    provider: 'xuanshu.IndependentLateZiSameDay',
    zi_day_rollover: '00:00_begins_next_day_pillar',
    zi_hour_stem_basis: '23:00_hour_stem_uses_next_civil_day_stem',
  };
}

function uncertaintyEventData(event) {
  const calendar = loadCalendar();
  const eventNames = {
    0: 'start_new_moon_review',
    1: 'end_new_moon_review',
    2: 'major_term_near_midnight_review',
    3: 'major_term_model_guard_changes_month_membership',
  };
  return {
    event: eventNames[event.eventType],
    utc: utcIsoFromMilliseconds(event.milliseconds),
    time_scale: 'TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY',
    term: event.termIndex < 0 ? null : calendar.termNames[event.termIndex],
    midnight_margin_seconds: event.marginMilliseconds / 1000,
    model_guard_seconds: event.guardSeconds,
    delta_t_source_code: calendar.sourceNames[String(event.sourceCode)],
    changes_calendar_assignment: event.changesAssignment,
    alternative_beijing_day_delta: event.alternativeDayDelta,
  };
}

function lunarBoundaryUncertainty(row, beijingDay) {
  const calendar = loadCalendar();
  const events = calendar.uncertaintyByStartDay.get(row.startDay) || [];
  const dayInMonth = beijingDay - row.startDay + 1;
  const relevant = [];
  let modelAmbiguous = false;
  let historicalAmbiguous = false;
  let reviewOnly = false;
  for (const event of events) {
    let applies = false;
    if (event.eventType === 0) applies = true;
    if (event.eventType === 1) {
      applies = event.alternativeDayDelta === -1 && dayInMonth >= row.length;
    }
    if (event.eventType === 2) {
      applies = beijingDay === Math.floor((event.milliseconds + BEIJING_OFFSET_MS) / DAY_MS);
    }
    if (event.eventType === 3) applies = true;
    if (!applies) continue;
    relevant.push(uncertaintyEventData(event));
    if (event.changesAssignment) modelAmbiguous = true;
    else reviewOnly = true;
  }
  if ((row.flags & 16) !== 0) historicalAmbiguous = true;
  if ((row.flags & 32) !== 0 && dayInMonth >= row.length) historicalAmbiguous = true;
  const divergenceFacts = calendar.data.validation_facts.historical_month_start_date_divergences || [];
  const relevantDivergences = divergenceFacts.filter((fact) => {
    const nominalDay = Math.floor(Date.parse(`${fact.nominal_month_start_beijing_date}T00:00:00Z`) / DAY_MS);
    return ((row.flags & 16) !== 0 && nominalDay === row.startDay) ||
      ((row.flags & 32) !== 0 && dayInMonth >= row.length && nominalDay === row.startDay + row.length);
  });
  const codes = [];
  if (historicalAmbiguous) codes.push('HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE');
  if (modelAmbiguous) codes.push('LUNAR_BOUNDARY_MODEL_GUARD');
  if (reviewOnly && !modelAmbiguous) codes.push('NEAR_MIDNIGHT_REVIEW');
  let status = 'CLEAR';
  if (historicalAmbiguous && modelAmbiguous) status = 'MULTIPLE_BOUNDARY_UNCERTAINTIES';
  else if (historicalAmbiguous) status = 'HISTORICAL_CONVENTION_DIVERGENCE';
  else if (modelAmbiguous) status = 'MODEL_GUARD_CROSSES_BEIJING_MIDNIGHT';
  else if (reviewOnly) status = 'REVIEW_ONLY';
  return {
    status,
    codes,
    affects_this_nominal_date: historicalAmbiguous || modelAmbiguous,
    reverse_conversion_blocked: historicalAmbiguous || modelAmbiguous,
    unresolved_result_change_without_enumerated_variant: historicalAmbiguous || modelAmbiguous,
    near_midnight_review_seconds: calendar.data.uncertainty.near_midnight_review_seconds,
    nominal_beijing_date: partsFromUnixDay(beijingDay),
    nominal_month_start_beijing_date: partsFromUnixDay(row.startDay),
    start_model_guard_seconds: row.startGuardSeconds,
    start_delta_t_source_code: calendar.sourceNames[String(row.sourceCode)],
    start_time_scale: 'TT_MINUS_FROZEN_DELTAT_AS_UT1_PROXY',
    hko_authority_divergences: relevantDivergences,
    events: relevant,
  };
}

function lunarDateData(beijingParts) {
  const day = unixDayFromParts(beijingParts);
  const { row } = findMonthByDay(day);
  const lunarDay = day - row.startDay + 1;
  const monthName = `${row.leap ? '闰' : ''}${LUNAR_MONTH_NAMES[row.month - 1]}`;
  return {
    year: row.lunarYear,
    month: row.month,
    day: lunarDay,
    leap_month: row.leap,
    display: `农历${yearGanzhi(row.lunarYear).name}年${monthName}${LUNAR_DAY_NAMES[lunarDay - 1]}`,
    boundary_uncertainty: lunarBoundaryUncertainty(row, day),
  };
}

function daysInMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function addSymbolic(parts, interval) {
  let second = parts.second;
  let minute = parts.minute + interval.minutes;
  let hour = parts.hour + interval.hours;
  let day = parts.day + interval.days;
  minute += Math.floor(second / 60);
  second %= 60;
  hour += Math.floor(minute / 60);
  minute %= 60;
  day += Math.floor(hour / 24);
  hour %= 24;
  let monthIndex = (parts.year + interval.years) * 12 + (parts.month - 1) + interval.months;
  let year = Math.floor(monthIndex / 12);
  let month = modulo(monthIndex, 12) + 1;
  let count = daysInMonth(year, month);
  while (day > count) {
    day -= count;
    monthIndex += 1;
    year = Math.floor(monthIndex / 12);
    month = modulo(monthIndex, 12) + 1;
    count = daysInMonth(year, month);
  }
  return { year, month, day, hour, minute, second, microsecond: 0 };
}

function hourBranchIndexForSect1(parts) {
  return parts.hour === 23 ? 11 : Math.floor((parts.hour + 1) / 2);
}

function providerInterval(provider, seconds, birthParts, termParts) {
  if (provider === 'default') {
    let remainder = seconds;
    const years = Math.floor(remainder / 259200); remainder %= 259200;
    const months = Math.floor(remainder / 21600); remainder %= 21600;
    const days = Math.floor(remainder / 720); remainder %= 720;
    const hours = Math.floor(remainder / 30); remainder %= 30;
    return { years, months, days, hours, minutes: remainder * 2 };
  }
  if (provider === 'china95' || provider === 'lunar_sect2') {
    let minutes = Math.floor(seconds / 60);
    const years = Math.floor(minutes / 4320); minutes %= 4320;
    const months = Math.floor(minutes / 360); minutes %= 360;
    const days = Math.floor(minutes / 12); minutes %= 12;
    return {
      years, months, days,
      hours: provider === 'lunar_sect2' ? minutes * 2 : 0,
      minutes: 0,
    };
  }
  if (provider === 'lunar_sect1') {
    const birthSerial = birthParts.epochMicroseconds;
    const termSerial = termParts.epochMicroseconds;
    const start = birthSerial <= termSerial ? birthParts : termParts;
    const end = birthSerial <= termSerial ? termParts : birthParts;
    let hourDifference = hourBranchIndexForSect1(end) - hourBranchIndexForSect1(start);
    let dayDifference = unixDayFromParts(end) - unixDayFromParts(start);
    if (hourDifference < 0) {
      hourDifference += 12;
      dayDifference -= 1;
    }
    const monthDifference = Math.floor(hourDifference * 10 / 30);
    let totalMonths = dayDifference * 4 + monthDifference;
    const days = hourDifference * 10 - monthDifference * 30;
    const years = Math.floor(totalMonths / 12);
    totalMonths -= years * 12;
    return { years, months: totalMonths, days, hours: 0, minutes: 0 };
  }
  inputError('INVALID_CORE_REQUEST', `Unsupported child_limit_provider: ${provider}`);
}

function childLimitData(
  item,
  gender,
  provider,
  decadeCount,
  absolute,
  yearPillar,
  monthPillar,
  birthParts,
  termSelectionMicroseconds
) {
  if (gender === null || gender === undefined) return null;
  const forward = (yearPillar.stemIndex % 2 === 0 && gender === 'man') ||
    (yearPillar.stemIndex % 2 === 1 && gender === 'woman');
  const previousJie = latestTermMatching(termSelectionMicroseconds, (term) => term.index % 2 === 1);
  const selected = forward
    ? nextTermMatching(previousJie.index, (term) => term.index % 2 === 1).term
    : previousJie.term;
  const roundedTermMilliseconds = Math.round(selected.milliseconds / 1000) * 1000;
  const termDate = new Date(roundedTermMilliseconds + BEIJING_OFFSET_MS);
  const termParts = {
    year: termDate.getUTCFullYear(), month: termDate.getUTCMonth() + 1,
    day: termDate.getUTCDate(), hour: termDate.getUTCHours(),
    minute: termDate.getUTCMinutes(), second: termDate.getUTCSeconds(), microsecond: 0,
    epochMicroseconds: (roundedTermMilliseconds + BEIJING_OFFSET_MS) * 1000,
  };
  const seconds = Math.abs(Math.round(selected.milliseconds / 1000) -
    Math.round(absolute.epochMicroseconds / 1000000));
  const interval = providerInterval(provider, seconds, birthParts, termParts);
  const symbolic = addSymbolic(birthParts, interval);
  const symbolicMilliseconds = Date.UTC(
    symbolic.year, symbolic.month - 1, symbolic.day,
    symbolic.hour - 8, symbolic.minute, symbolic.second
  );
  const firstAge = symbolic.year - birthParts.year + 1;
  const step = forward ? 1 : -1;
  const decades = [];
  for (let index = 0; index < decadeCount; index += 1) {
    const pillar = ganzhi(monthPillar.index + step * (index + 1));
    const startYear = symbolic.year + index * 10;
    const startAge = firstAge + index * 10;
    decades.push({
      index: index + 1,
      ganzhi: pillar.name,
      start_age: startAge,
      end_age: startAge + 9,
      start_year: startYear,
      start_year_ganzhi: yearGanzhi(startYear).name,
      end_year: startYear + 9,
      end_year_ganzhi: yearGanzhi(startYear + 9).name,
    });
  }
  return {
    gender_parameter: gender,
    direction: forward ? 'forward' : 'backward',
    provider,
    age_convention: 'provider_traditional_nominal_age',
    interval,
    selected_jie: termData(selected),
    symbolic_start_beijing_time_under_provider: localIso(symbolic),
    symbolic_start_utc_under_provider: utcIsoFromMilliseconds(symbolicMilliseconds),
    decades,
  };
}

function engineMetadata() {
  const calendar = loadCalendar();
  return {
    name: 'xuanshu-four-pillars-core',
    version: ENGINE_VERSION,
    calendar_dataset_sha256: calendar.dataSha256,
    node_core_sha256: calendar.nodeCoreSha256,
    source: {
      ephemeris: calendar.data.sources.ephemeris,
      generator: calendar.data.sources.generator,
      delta_t: {
        historical: calendar.data.sources.delta_t_historical,
        measured: calendar.data.sources.delta_t_measured,
        predictions: calendar.data.sources.delta_t_predictions,
        context_scenario: calendar.data.sources.delta_t_context_scenario,
      },
      runtime: 'frozen_fact_lookup_and_independent_traditional_mappings',
    },
    coverage: calendar.data.coverage,
    uncertainty: calendar.data.uncertainty,
  };
}

function computeCase(item, request, variant = null, outputId = item.id) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    inputError('INVALID_CORE_REQUEST', 'Each chart case must be an object');
  }
  if (typeof item.id !== 'string' || item.id.length === 0) {
    inputError('INVALID_CORE_REQUEST', 'Each chart case requires a nonempty id');
  }
  assertAllowedKeys(item, new Set([
    'id', 'label', 'absolute_utc', 'beijing_time', 'local_basis_time', 'time_basis',
    'day_boundary', 'solar_review_offset_seconds', 'scenario_kind',
  ]), 'chart case');
  if (item.label !== undefined && typeof item.label !== 'string') {
    inputError('INVALID_CORE_REQUEST', 'Chart case label must be a string');
  }
  if (!['civil_clock', 'local_mean_solar', 'local_apparent_solar'].includes(item.time_basis)) {
    inputError('INVALID_CORE_REQUEST', `Unsupported time_basis: ${item.time_basis}`);
  }
  if (!['input_candidate', 'sensitivity_bracket'].includes(item.scenario_kind || 'input_candidate')) {
    inputError('INVALID_CORE_REQUEST', `Unsupported scenario_kind: ${item.scenario_kind}`);
  }
  if (item.solar_review_offset_seconds !== undefined &&
      (!Number.isFinite(item.solar_review_offset_seconds) ||
       !Number.isInteger(item.solar_review_offset_seconds))) {
    inputError('INVALID_CORE_REQUEST', 'solar_review_offset_seconds must be an integer');
  }
  const absolute = parseIso(item.absolute_utc, { requireZ: true, label: 'absolute_utc' });
  const beijing = parseIso(item.beijing_time, { label: 'beijing_time' });
  const basis = parseIso(item.local_basis_time, { label: 'local_basis_time' });
  if (absolute.epochMicroseconds + BEIJING_OFFSET_MS * 1000 !== beijing.epochMicroseconds) {
    inputError('INCONSISTENT_ABSOLUTE_AND_BEIJING_TIME',
      'absolute_utc plus eight hours must exactly equal beijing_time');
  }
  if (beijing.year < 1900 || beijing.year > 2034) {
    inputError('UNSUPPORTED_CALENDAR_RANGE',
      'The Beijing calendar frame must remain inside the frozen 1900 through 2034 context');
  }
  if (basis.year < 1900 || basis.year > 2034) {
    inputError('UNSUPPORTED_CALENDAR_RANGE',
      'local_basis_time must remain inside the frozen 1900 through 2034 context');
  }
  const termSelectionMicroseconds = variant === null
    ? absolute.epochMicroseconds
    : variant.boundary.milliseconds * 1000 +
      (variant.state === 'birth_before_term' ? -1 : 1);
  const absoluteChart = absolutePillars(termSelectionMicroseconds);
  const localChart = localDayHourPillars(basis, item.day_boundary);
  const dayStemIndex = localChart.day.stemIndex;
  const context = termContext(termSelectionMicroseconds);
  const chartName = [absoluteChart.year, absoluteChart.month, localChart.day, localChart.hour]
    .map((pillar) => pillar.name).join(' ');
  return {
    id: outputId,
    source_case_id: item.id,
    label: item.label,
    calendar_model_variant: variant === null
      ? null
      : calendarModelVariantData(variant.boundary, variant.state),
    solar_term_boundary_uncertainty: solarTermBoundaryUncertainty(
      variant === null ? null : variant.boundary,
      absolute.epochMicroseconds,
      variant === null ? null : variant.state
    ),
    conventions: {
      term_frame: 'absolute_instant_against_frozen_TT_minus_DeltaT_UT1_proxy_events',
      calendar_day_frame: 'fixed_UTC+08:00',
      day_hour_time_basis: item.time_basis,
      day_boundary: item.day_boundary,
      zi_policy: ziPolicyData(item.day_boundary),
      solar_review_offset_seconds: item.solar_review_offset_seconds || 0,
      scenario_kind: item.scenario_kind || 'input_candidate',
    },
    normalized_times: {
      absolute_utc: item.absolute_utc,
      beijing_calendar_frame: item.beijing_time,
      local_basis: item.local_basis_time,
    },
    lunar_date_beijing_frame: lunarDateData(beijing),
    solar_terms: {
      previous_or_current: termData(context.current),
      next: termData(context.next),
    },
    chart: {
      ganzhi: chartName,
      ganzhi_evidence_layer: 'L1B_VERSIONED_CALENDAR',
      derived_field_evidence_layer: 'L1C_VERSIONED_TRADITIONAL_MAP',
      year: pillarData('year', absoluteChart.year, dayStemIndex),
      month: pillarData('month', absoluteChart.month, dayStemIndex),
      day: pillarData('day', localChart.day, dayStemIndex),
      hour: pillarData('hour', localChart.hour, dayStemIndex),
    },
    dayun: childLimitData(
      item,
      request.gender ?? null,
      request.child_limit_provider,
      request.decade_count,
      absolute,
      absoluteChart.year,
      absoluteChart.month,
      beijing,
      termSelectionMicroseconds
    ),
  };
}

function lunarRowsForLabel(lunar) {
  const calendar = loadCalendar();
  return calendar.months.filter((row) =>
    row.lunarYear === lunar.year && row.month === lunar.month && row.leap === lunar.leap_month
  );
}

function assertLunarConversionIsUnambiguous(row, requestedDay) {
  const calendar = loadCalendar();
  const events = calendar.uncertaintyByStartDay.get(row.startDay) || [];
  const historicalStart = (row.flags & 16) !== 0;
  const historicalEnd = (row.flags & 32) !== 0 && requestedDay >= row.length;
  if (historicalStart || historicalEnd) {
    inputError('HISTORICAL_CALENDAR_AUTHORITY_DIVERGENCE',
      'The requested lunar label differs under a verified historical calendar authority; reverse conversion is intentionally blocked');
  }
  const modelStart = events.some((event) =>
    (event.eventType === 0 || event.eventType === 3) && event.changesAssignment
  );
  const modelEnd = events.some((event) =>
    event.eventType === 1 && event.changesAssignment &&
    ((event.alternativeDayDelta === -1 && requestedDay >= row.length) ||
     (event.alternativeDayDelta === 1 && requestedDay > row.length))
  );
  if (modelStart || modelEnd) {
    inputError('LUNAR_BOUNDARY_MODEL_GUARD',
      'The requested lunar label crosses Beijing midnight under the event-specific model guard; reverse conversion is intentionally blocked');
  }
}

function convertLunar(request) {
  assertAllowedKeys(request, new Set(['mode', 'lunar', 'time']), 'convert_lunar request');
  const lunar = request.lunar || {};
  assertAllowedKeys(lunar, new Set(['year', 'month', 'day', 'leap_month']), 'lunar date');
  if (!Number.isInteger(lunar.year) || !Number.isInteger(lunar.month) || !Number.isInteger(lunar.day)) {
    inputError('INVALID_LUNAR_DATE', 'lunar year, month, and day must be integers');
  }
  if (typeof lunar.leap_month !== 'boolean') {
    inputError('INVALID_LUNAR_DATE', 'lunar leap_month must be a boolean');
  }
  if (lunar.year < 1900 || lunar.year > 2033 || lunar.month < 1 || lunar.month > 12 ||
      lunar.day < 1 || lunar.day > 30) {
    inputError('INVALID_LUNAR_DATE', 'lunar date is outside the supported range');
  }
  const rows = lunarRowsForLabel(lunar);
  if (rows.length !== 1) inputError('INVALID_LUNAR_DATE', 'The requested lunar month does not exist');
  const row = rows[0];
  assertLunarConversionIsUnambiguous(row, lunar.day);
  if (lunar.day > row.length) inputError('INVALID_LUNAR_DATE', 'The requested lunar day does not exist');
  const targetDay = row.startDay + lunar.day - 1;
  const publicStartDay = Math.floor(Date.UTC(1901, 0, 1) / DAY_MS);
  const publicEndDay = Math.floor(Date.UTC(2033, 11, 31) / DAY_MS);
  if (targetDay < publicStartDay || targetDay > publicEndDay) {
    inputError('LUNAR_DATE_OUTSIDE_GREGORIAN_COVERAGE',
      'The lunar label converts outside the supported fixed-UTC+8 Gregorian range 1901-01-01 through 2033-12-31');
  }
  const time = parseTimeOnly(request.time || '12:00:00');
  const solar = partsFromUnixDay(targetDay);
  const solarParts = {
    ...solar,
    hour: time.hour,
    minute: time.minute,
    second: time.second,
    microsecond: time.microsecond,
  };
  return {
    ok: true,
    schema_version: RESPONSE_SCHEMA,
    mode: 'convert_lunar',
    engine: engineMetadata(),
    conversion: {
      input_lunar: {
        year: lunar.year,
        month: lunar.month,
        day: lunar.day,
        leap_month: lunar.leap_month,
      },
      beijing_reference_solar_time: localIso(solarParts),
      boundary_uncertainty: lunarBoundaryUncertainty(row, targetDay),
    },
  };
}

function charts(request) {
  assertAllowedKeys(request, new Set([
    'mode', 'gender', 'child_limit_provider', 'decade_count', 'cases',
  ]), 'charts request');
  if (!Array.isArray(request.cases) || request.cases.length === 0) {
    inputError('INVALID_CORE_REQUEST', 'At least one case is required');
  }
  if (!Number.isInteger(request.decade_count) || request.decade_count < 1 || request.decade_count > 20) {
    inputError('INVALID_CORE_REQUEST', 'decade_count must be an integer from 1 through 20');
  }
  if (!['default', 'china95', 'lunar_sect1', 'lunar_sect2'].includes(request.child_limit_provider)) {
    inputError('INVALID_CORE_REQUEST', 'Unsupported child_limit_provider');
  }
  if (![null, 'man', 'woman'].includes(request.gender ?? null)) {
    inputError('INVALID_CORE_REQUEST', 'gender must be null, man, or woman');
  }
  const ids = new Set();
  for (const item of request.cases) {
    if (!item || typeof item.id !== 'string' || ids.has(item.id)) {
      inputError('INVALID_CORE_REQUEST', 'Chart case ids must be unique nonempty strings');
    }
    ids.add(item.id);
  }
  const outputIds = new Set(ids);
  const outputCases = [];
  for (const item of request.cases) {
    const absolute = parseIso(item.absolute_utc, { requireZ: true, label: 'absolute_utc' });
    const boundaries = calendarModelBoundaryTerms(absolute.epochMicroseconds);
    if (boundaries.length > 1) {
      inputError('CALENDAR_BOUNDARY_UNRESOLVED',
        'More than one guarded Jie can change this chart and no exhaustive variant set is encoded');
    }
    if (boundaries.length === 0) {
      outputCases.push(computeCase(item, request));
      continue;
    }
    const boundary = boundaries[0];
    for (const state of ['birth_before_term', 'birth_after_term']) {
      const base = `${item.id}::calendar_model::${boundary.milliseconds}:${state}`;
      let outputId = base;
      let suffix = 1;
      while (outputIds.has(outputId)) {
        outputId = `${base}:${suffix}`;
        suffix += 1;
      }
      outputIds.add(outputId);
      outputCases.push(computeCase(item, request, { boundary, state }, outputId));
    }
  }
  return {
    ok: true,
    schema_version: RESPONSE_SCHEMA,
    mode: 'charts',
    engine: engineMetadata(),
    cases: outputCases,
  };
}

function handle(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    inputError('INVALID_CORE_REQUEST', 'Top-level request must be an object');
  }
  if (request.mode === 'convert_lunar') return convertLunar(request);
  if (request.mode === 'charts') return charts(request);
  inputError('INVALID_CORE_REQUEST', `Unsupported mode: ${request.mode}`);
}

function readRequest() {
  const bytes = process.argv[2] ? fs.readFileSync(process.argv[2]) : fs.readFileSync(0);
  if (bytes.length > MAX_INPUT_BYTES) inputError('INVALID_CORE_REQUEST', 'Core request exceeds 4 MiB');
  return strictJson(bytes, 'Core request');
}

function writeJson(value, stream) {
  const text = `${JSON.stringify(value)}\n`;
  if (Buffer.byteLength(text, 'utf8') > MAX_OUTPUT_BYTES) {
    runtimeError('Core response exceeds 32 MiB');
  }
  stream.write(text);
}

try {
  writeJson(handle(readRequest()), process.stdout);
} catch (error) {
  const coreError = error instanceof CoreError
    ? error
    : new CoreError('runtime', 'INTERNAL_CORE_ERROR', error.message || String(error));
  const payload = {
    ok: false,
    error: { kind: coreError.kind, code: coreError.code, message: coreError.message },
  };
  try {
    const text = `${JSON.stringify(payload)}\n`;
    process.stderr.write(text);
  } catch (_writeError) {
    process.stderr.write('{"ok":false,"error":{"kind":"runtime","code":"INTERNAL_CORE_ERROR","message":"Failed to serialize core error"}}\n');
  }
  process.exitCode = 1;
}
