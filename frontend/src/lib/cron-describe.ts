const DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function parseList(part: string, min: number, max: number): number[] | null {
  if (part === "*") return null;
  const out: number[] = [];
  for (const chunk of part.split(",")) {
    const stepMatch = chunk.match(/^(\*|\d+(?:-\d+)?)\/(\d+)$/);
    if (stepMatch) {
      const range = stepMatch[1];
      const step = Number(stepMatch[2]);
      if (!Number.isFinite(step) || step < 1) return [];
      let a = min;
      let b = max;
      if (range !== "*") {
        const [lo, hi] = range.split("-").map(Number);
        a = lo;
        b = hi ?? lo;
      }
      for (let i = a; i <= b; i += step) out.push(i);
      continue;
    }
    if (chunk.includes("-")) {
      const [a, b] = chunk.split("-").map(Number);
      if (!Number.isFinite(a) || !Number.isFinite(b) || a < min || b > max || a > b) return [];
      for (let i = a; i <= b; i++) out.push(i);
      continue;
    }
    const n = Number(chunk);
    if (!Number.isFinite(n) || n < min || n > max) return [];
    out.push(n);
  }
  return out;
}

function joinList(items: string[]): string {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function clock(hour: number, minute: number): string {
  return `${pad2(hour)}:${pad2(minute)}`;
}

function fieldPhrase(
  values: number[] | null,
  everyLabel: string,
  nameOf: (n: number) => string,
  unit: string,
): string | null {
  if (values == null) return null;
  if (values.length === 0) return "";
  const unique = [...new Set(values)].sort((a, b) => a - b);
  if (unique.length === maxSpan(unique) && unique.length > 2) {
    return `${everyLabel} from ${nameOf(unique[0])} through ${nameOf(unique[unique.length - 1])}`;
  }
  return `${unit} ${joinList(unique.map(nameOf))}`;
}

function maxSpan(unique: number[]): number {
  return unique[unique.length - 1] - unique[0] + 1;
}

/** English summary of a 5-field Unix cron expression, or null if it cannot be parsed. */
export function describeCron(expression: string): string | null {
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [minP, hourP, domP, monP, dowP] = parts;
  const minutes = parseList(minP, 0, 59);
  const hours = parseList(hourP, 0, 23);
  const doms = parseList(domP, 1, 31);
  const months = parseList(monP, 1, 12);
  const dows = parseList(dowP.replace(/7/g, "0"), 0, 6);
  if (minutes?.length === 0 || hours?.length === 0 || doms?.length === 0 || months?.length === 0 || dows?.length === 0) {
    return null;
  }

  let when: string;
  if (minutes == null && hours == null) {
    when = "every minute";
  } else if (minutes == null && hours != null && hours.length === 1) {
    when = `every minute during hour ${pad2(hours[0])}`;
  } else if (minutes != null && minutes.length === 1 && hours == null) {
    when = `every hour at minute ${pad2(minutes[0])}`;
  } else if (minutes != null && minutes.length === 1 && hours != null && hours.length === 1) {
    when = `at ${clock(hours[0], minutes[0])}`;
  } else if (minutes != null && minutes.length === 1 && hours != null) {
    when = `at minute ${pad2(minutes[0])} of ${joinList(hours.map((h) => `${pad2(h)}:00`))}`;
  } else if (minP.startsWith("*/") && hours == null && minutes != null) {
    when = `every ${minP.slice(2)} minutes`;
  } else if (hourP.startsWith("*/") && minutes != null && minutes.length === 1 && hours != null) {
    when = `every ${hourP.slice(2)} hours at minute ${pad2(minutes[0])}`;
  } else {
    const minText = minutes == null ? "every minute" : `minute ${joinList(minutes.map(pad2))}`;
    const hourText = hours == null ? "every hour" : `hour ${joinList(hours.map(pad2))}`;
    when = `${minText}, ${hourText}`;
  }

  const dayBits: string[] = [];
  const weekdayPhrase = fieldPhrase(dows, "every day", (n) => DOW[n] ?? String(n), "on");
  const monthDayPhrase = fieldPhrase(doms, "every day of the month", String, "on day");
  if (weekdayPhrase) dayBits.push(weekdayPhrase.replace(/^on /, "on "));
  if (monthDayPhrase && doms != null) dayBits.push(monthDayPhrase);
  const monthPhrase = fieldPhrase(months, "every month", (n) => MON[n - 1] ?? String(n), "in");

  const days =
    dayBits.length === 0
      ? "every day"
      : dayBits.length === 2
        ? `${dayBits[0]} and ${dayBits[1]}`
        : dayBits[0];

  const monthBit = monthPhrase ? `, ${monthPhrase}` : "";
  const sentence = `${when}, ${days}${monthBit}`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}
