import { describe, expect, it } from "vitest";
import { dur, fmt, passes } from "./format";

describe("format", () => {
  it("never shows a number without its unit and shows missing as a dash", () => {
    expect(fmt(812.4, "ms", 0)).toBe("812 ms");
    expect(fmt(97.5, "%")).toBe("97.5%");
    expect(fmt(null, "ms")).toBe("—");
  });
  it("judges a value against its threshold in the right direction", () => {
    expect(passes(900, 1500, "lower_is_better")).toBe(true);
    expect(passes(96, 97, "higher_is_better")).toBe(false);
    expect(passes(null, 1500, "lower_is_better")).toBeNull();
  });
  it("formats durations", () => {
    expect(dur(65_000)).toBe("1m 05s");
  });
});
