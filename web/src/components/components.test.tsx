import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";

import { Button, ConfirmDialog, DataTable, MoneyInput, PinInput, StatusBadge, Tabs, TextField } from ".";

describe("Button", () => {
  it("is a real button and announces loading", () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    expect(btn).toHaveAttribute("type", "button");
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(
      <Button onClick={onClick} loading>
        Save
      </Button>,
    );
    const busy = screen.getByRole("button", { name: /Save/ });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Please wait")).toBeInTheDocument();
  });

  it("uses the destructive style for destructive actions (not the emergency red)", () => {
    render(<Button variant="destructive">Delete</Button>);
    const cls = screen.getByRole("button", { name: "Delete" }).className;
    expect(cls).toContain("bg-danger-500");
    expect(cls).not.toContain("emergency");
  });
});

describe("TextField", () => {
  it("links label, hint and error to the input", () => {
    render(<TextField label="Property name" hint="e.g. Palm Court" error="This field is required." />);
    const input = screen.getByLabelText("Property name");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("This field is required. e.g. Palm Court");
  });

  it("marks optional fields in the label", () => {
    render(<TextField label="Email" optional />);
    expect(screen.getByLabelText("Email (optional)")).toBeInTheDocument();
  });
});

describe("MoneyInput", () => {
  function Harness({ onValue }: { onValue: (v: string) => void }) {
    const [v, setV] = useState("");
    return (
      <MoneyInput
        label="Amount"
        value={v}
        onChange={(x) => {
          setV(x);
          onValue(x);
        }}
      />
    );
  }

  it("has a label, a decimal keypad and tidies the amount on blur", () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    const input = screen.getByLabelText("Amount");
    expect(input).toHaveAttribute("inputmode", "decimal");
    fireEvent.change(input, { target: { value: "1500000abc" } });
    expect(input).toHaveValue("1500000");
    fireEvent.blur(input);
    expect(input).toHaveValue("1,500,000.00");
  });
});

describe("PinInput", () => {
  function Harness() {
    const [v, setV] = useState("");
    return <PinInput label="6-digit PIN" value={v} onChange={setV} />;
  }

  it("accepts digits only, hides them, and has a show/hide toggle", () => {
    render(<Harness />);
    const input = screen.getByLabelText("6-digit PIN");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("inputmode", "numeric");
    fireEvent.change(input, { target: { value: "12ab34567" } });
    expect(input).toHaveValue("123456");
    const toggle = screen.getByRole("button", { name: "Show PIN" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveTextContent("Hide");
  });
});

describe("StatusBadge", () => {
  it("shows plain-language labels", () => {
    render(
      <>
        <StatusBadge status="part_paid" />
        <StatusBadge status="void" />
        <StatusBadge status="overdue" />
      </>,
    );
    expect(screen.getByText("Part paid")).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  it("is a labelled modal that closes on Escape", () => {
    const onClose = vi.fn();
    render(<ConfirmDialog open onClose={onClose} onConfirm={vi.fn()} title="Waive this charge?" confirmLabel="Waive" />);
    const dialog = screen.getByRole("dialog", { name: "Waive this charge?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Tabs", () => {
  it("moves between tabs with the arrow keys", () => {
    function Harness() {
      const [v, setV] = useState("a");
      return (
        <Tabs
          label="Sections"
          value={v}
          onChange={setV}
          items={[
            { id: "a", label: "Leases", content: <p>Leases panel</p> },
            { id: "b", label: "Charges", content: <p>Charges panel</p> },
          ]}
        />
      );
    }
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole("tab", { name: "Leases" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Charges" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Charges panel");
  });
});

describe("DataTable", () => {
  const columns = [{ key: "name", header: "Name", cell: (r: { name: string }) => r.name }];
  it("renders rows, empty and error states", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <MemoryRouter>
        <DataTable caption="People" columns={columns} rows={[{ name: "Ada" }]} rowKey={(r) => r.name} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("table", { name: "People" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /Ada/ })).toBeInTheDocument();

    rerender(<DataTable caption="People" columns={columns} rows={[]} rowKey={(r) => r.name} empty={{ title: "Nobody yet" }} />);
    expect(screen.getByRole("heading", { name: "Nobody yet" })).toBeInTheDocument();

    rerender(<DataTable caption="People" columns={columns} rows={undefined} rowKey={(r) => r.name} error={new Error("x")} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
