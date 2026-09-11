import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GradeChip } from "./GradeChip";

describe("GradeChip", () => {
  it("renders the grade", () => {
    render(<GradeChip grade="B" />);
    expect(screen.getByText("B")).toBeInTheDocument();
  });
  it("never invents a grade: a suppressed grade is a dash with its reason", () => {
    render(<GradeChip grade={null} reason="insufficient sample" />);
    expect(screen.getByTitle("insufficient sample")).toHaveTextContent("—");
  });
});
