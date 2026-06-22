import { describe, expect, it } from "vitest";

import { validateLead, type LeadFields } from "../src/validation";

const valid: LeadFields = {
  name: "Asha",
  email: "a@b.co",
  phone: "",
  consent: true,
  message: "",
};

const fieldsOf = (f: Partial<LeadFields>) => validateLead({ ...valid, ...f }).map((e) => e.field);

describe("validateLead (mirrors the backend rules)", () => {
  it("accepts a valid lead", () => {
    expect(validateLead(valid)).toEqual([]);
  });

  it("requires a name", () => {
    expect(fieldsOf({ name: "   " })).toContain("name");
  });

  it("rejects an invalid email with no phone", () => {
    const errors = validateLead({ ...valid, email: "asdf@asdf" });
    expect(errors.find((e) => e.field === "email")?.code).toBe("invalid");
  });

  it("rejects an implausible phone", () => {
    const errors = validateLead({ ...valid, email: "", phone: "1234567" });
    expect(errors.find((e) => e.field === "phone")?.code).toBe("invalid");
  });

  it("accepts a phone-only lead", () => {
    expect(validateLead({ ...valid, email: "", phone: "9876543210" })).toEqual([]);
  });

  it("requires a contact channel when both are blank", () => {
    expect(fieldsOf({ email: "", phone: "" })).toContain("contact");
  });

  it("requires consent", () => {
    expect(fieldsOf({ consent: false })).toContain("consent");
  });

  it("caps message length at 1,000", () => {
    expect(fieldsOf({ message: "x".repeat(1001) })).toContain("message");
  });
});
