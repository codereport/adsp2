const assert = require("node:assert/strict");
const test = require("node:test");
const {addMonthsUTC, elapsedSince} = require("../assets/js/tssp.js");

const published = new Date("2026-08-21T00:00:00Z");

test("splits elapsed time into calendar months and the remaining units", () => {
  assert.deepEqual(elapsedSince(published, new Date("2026-11-06T17:55:21Z")), {
    months: 2, weeks: 2, days: 2, hours: 17, minutes: 55, seconds: 21, state: "normal"
  });
});

test("waits for the monthly anniversary instead of approximating months as days", () => {
  assert.deepEqual(elapsedSince(published, new Date("2026-09-20T23:59:59Z")), {
    months: 0, weeks: 4, days: 2, hours: 23, minutes: 59, seconds: 59, state: "normal"
  });
});

test("warns strictly after ten calendar months", () => {
  assert.equal(elapsedSince(published, new Date("2027-06-21T00:00:00Z")).state, "normal");
  assert.equal(elapsedSince(published, new Date("2027-06-21T00:00:01Z")).state, "warning");
});

test("turns red strictly after the one-year anniversary", () => {
  assert.equal(elapsedSince(published, new Date("2027-08-21T00:00:00Z")).state, "warning");
  assert.equal(elapsedSince(published, new Date("2027-08-21T00:00:01Z")).state, "danger");
});

test("clamps month-end anniversaries and preserves the publication time", () => {
  const date = new Date("2025-01-31T12:34:56.789Z");
  assert.equal(addMonthsUTC(date, 1).toISOString(), "2025-02-28T12:34:56.789Z");
  assert.equal(addMonthsUTC(date, 2).toISOString(), "2025-03-31T12:34:56.789Z");
  assert.equal(date.toISOString(), "2025-01-31T12:34:56.789Z");
});

test("handles leap-year month and year anniversaries", () => {
  assert.equal(addMonthsUTC(new Date("2024-01-31T00:00:00Z"), 1).toISOString(), "2024-02-29T00:00:00.000Z");
  const leapDay = new Date("2024-02-29T00:00:00Z");
  assert.equal(addMonthsUTC(leapDay, 12).toISOString(), "2025-02-28T00:00:00.000Z");
  assert.equal(elapsedSince(leapDay, new Date("2025-02-28T00:00:01Z")).state, "danger");
});

test("uses UTC elapsed days across daylight-saving changes", () => {
  assert.deepEqual(elapsedSince(new Date("2026-03-07T00:00:00Z"), new Date("2026-03-09T00:00:00Z")), {
    months: 0, weeks: 0, days: 2, hours: 0, minutes: 0, seconds: 0, state: "normal"
  });
});

test("never displays negative elapsed time if the visitor's clock is behind", () => {
  assert.deepEqual(elapsedSince(published, new Date("2026-08-20T23:59:59Z")), {
    months: 0, weeks: 0, days: 0, hours: 0, minutes: 0, seconds: 0, state: "normal"
  });
});
