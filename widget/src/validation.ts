// Client-side lead validation — mirrors the backend domain rules (FR-11/12) so the
// visitor gets instant inline feedback. The server re-validates regardless.

export interface LeadFields {
  name: string;
  email: string;
  phone: string;
  consent: boolean;
  message: string;
}

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^(?:\+91|0)?[6-9]\d{9}$/;
const MAX_MESSAGE = 1000;

const blank = (value: string): boolean => !value || value.trim() === "";

export const isValidEmail = (email: string): boolean => EMAIL_RE.test(email.trim());
export const isValidPhone = (phone: string): boolean =>
  PHONE_RE.test(phone.replace(/[\s\-()]/g, ""));

export function validateLead(fields: LeadFields): FieldError[] {
  const errors: FieldError[] = [];

  if (blank(fields.name)) {
    errors.push({ field: "name", code: "required", message: "Please enter your name." });
  }

  const emailPresent = !blank(fields.email);
  const phonePresent = !blank(fields.phone);
  const emailOk = emailPresent && isValidEmail(fields.email);
  const phoneOk = phonePresent && isValidPhone(fields.phone);

  if (emailPresent && !emailOk) {
    errors.push({ field: "email", code: "invalid", message: "Please enter a valid email address." });
  }
  if (phonePresent && !phoneOk) {
    errors.push({
      field: "phone",
      code: "invalid",
      message: "Please enter a valid 10-digit Indian mobile number.",
    });
  }
  if (!emailOk && !phoneOk && !emailPresent && !phonePresent) {
    errors.push({
      field: "contact",
      code: "contact_required",
      message: "Please provide a valid email address or phone number.",
    });
  }

  if (fields.message && fields.message.length > MAX_MESSAGE) {
    errors.push({
      field: "message",
      code: "too_long",
      message: `Please keep your message under ${MAX_MESSAGE} characters.`,
    });
  }

  if (!fields.consent) {
    errors.push({
      field: "consent",
      code: "required",
      message: "Please tick consent so Admissions can follow up with you.",
    });
  }

  return errors;
}
