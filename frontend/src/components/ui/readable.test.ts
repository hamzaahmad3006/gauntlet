import { describe, expect, it } from "vitest";
import { describeConditions, humanize, METRIC_UNITS, metricRank } from "./format";

describe("humanize", () => {
  it("turns an identifier into something a person reads", () => {
    expect(humanize("book_table_basic")).toBe("Book table basic");
    expect(humanize("calm_standard")).toBe("Calm standard");
  });
  it("leaves a missing key as a dash rather than printing undefined", () => {
    expect(humanize(undefined)).toBe("—");
    expect(humanize(null)).toBe("—");
    expect(humanize("")).toBe("—");
  });
});

describe("describeConditions", () => {
  it("says what each impairment stage does to the caller's audio", () => {
    const words = describeConditions({
      frame_loss: { loss_probability: 0.08, burst_length: 3 },
      jitter: { mean_ms: 80, stddev_ms: 40, max_ms: 300 },
      noise: { noise_bed: "cafe", snr_db: 12 },
      interruption: { interruptions_per_call: 2, offset_range_ms: [400, 1500] },
    });
    expect(words).toEqual([
      "8% packet loss, bursts of 3",
      "80 ± 40 ms jitter",
      "Cafe noise at 12 dB SNR",
      "2 interruptions per call",
    ]);
  });

  it("describes the clean profile as no impairment at all", () => {
    expect(describeConditions({})).toEqual([]);
    expect(describeConditions(null)).toEqual([]);
  });

  it("keeps the phrases in stage order, so mobile always reads the same way", () => {
    const mobile = { delay: { delay_ms: 60 }, frame_loss: { loss_probability: 0.03, burst_length: 2 },
                     jitter: { mean_ms: 40, stddev_ms: 20 } };
    expect(describeConditions(mobile)).toEqual([
      "3% packet loss, bursts of 2",
      "40 ± 20 ms jitter",
      "+60 ms delay",
    ]);
  });
});

describe("metric presentation", () => {
  it("gives every latency metric milliseconds and every rate a percent", () => {
    expect(METRIC_UNITS.response_latency_p95).toBe("ms");
    expect(METRIC_UNITS.barge_in_stop_p95).toBe("ms");
    expect(METRIC_UNITS.dead_air_ratio).toBe("%");
    expect(METRIC_UNITS.task_success_rate).toBe("%");
  });

  it("orders metric tables by what a caller feels first, rig diagnostics last", () => {
    const table = ["cache_hit_rate", "dead_air_ratio", "rig_overhead_p95", "response_latency_p95"];
    expect([...table].sort((a, b) => metricRank(a) - metricRank(b))).toEqual([
      "response_latency_p95", "dead_air_ratio", "cache_hit_rate", "rig_overhead_p95",
    ]);
  });

  it("puts a metric it has never seen at the end instead of first", () => {
    expect(metricRank("something_new")).toBeGreaterThan(metricRank("reconnect_rate"));
  });
});
