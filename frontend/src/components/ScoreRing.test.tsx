import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreRing } from "./ScoreRing";

describe("ScoreRing", () => {
  it("shows the grade and the score it was given", () => {
    render(<ScoreRing score={76.17} grade="C" />);
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("76.17 / 100")).toBeInTheDocument();
  });

  it("never draws a missing grade as a zero", () => {
    render(<ScoreRing score={null} grade={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("no grade")).toBeInTheDocument();
  });

  it("describes itself for a screen reader", () => {
    render(<ScoreRing score={100} grade="A" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Grade A, score 100 out of 100");
  });

  it("drops the decimals from a whole score", () => {
    render(<ScoreRing score={100} grade="A" />);
    expect(screen.getByText("100 / 100")).toBeInTheDocument();
  });
});
