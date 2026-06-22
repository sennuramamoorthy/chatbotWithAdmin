// The embeddable chat widget (US-10). Shadow-DOM isolated so it never clashes with
// the host page's styles; keyboard- and screen-reader-accessible; soft-fails to
// static Admissions contact when the backend is unreachable.

import type { ChatClient } from "./api";
import { validateLead, type LeadFields } from "./validation";

export interface Contact {
  email: string;
  phone: string;
  page: string;
}

export interface WidgetConfig {
  client: ChatClient;
  contact: Contact;
  sessionId: string;
}

const SOFT_FAIL = "Sorry — our assistant is unavailable right now. You can reach Admissions directly:";

const STYLE = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: system-ui, sans-serif; }
  .tk-bubble {
    position: fixed; right: 20px; bottom: 20px; width: 56px; height: 56px;
    border-radius: 50%; border: none; background: #1f4e8c; color: #fff;
    font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,.25);
  }
  .tk-panel {
    position: fixed; right: 20px; bottom: 88px;
    width: min(360px, calc(100vw - 40px)); height: min(540px, calc(100vh - 120px));
    display: flex; flex-direction: column; background: #fff; color: #1a1a1a;
    border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.28); overflow: hidden;
  }
  .tk-panel[hidden] { display: none; }
  .tk-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #1f4e8c; color: #fff; }
  .tk-title { font-weight: 600; flex: 1; }
  .tk-header button { background: rgba(255,255,255,.18); color: #fff; border: none; border-radius: 6px; padding: 4px 8px; cursor: pointer; }
  .tk-chat, .tk-lead { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .tk-chat[hidden], .tk-lead[hidden] { display: none; }
  .tk-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
  .tk-msg { padding: 8px 10px; border-radius: 10px; max-width: 85%; white-space: pre-wrap; }
  .tk-msg-user { align-self: flex-end; background: #e4ecf7; }
  .tk-msg-bot { align-self: flex-start; background: #f1f1f1; }
  .tk-contact { font-size: 13px; background: #fff6e0; padding: 8px 10px; border-radius: 8px; }
  .tk-lead-offer { align-self: flex-start; background: #1f4e8c; color: #fff; border: none; border-radius: 8px; padding: 6px 10px; cursor: pointer; }
  .tk-composer { display: flex; gap: 6px; padding: 10px; border-top: 1px solid #eee; }
  .tk-input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 8px; }
  .tk-send { background: #1f4e8c; color: #fff; border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; }
  .tk-lead { padding: 12px; overflow-y: auto; gap: 8px; }
  .tk-lead label { font-size: 13px; display: block; margin-top: 6px; }
  .tk-lead input, .tk-lead textarea { width: 100%; padding: 7px; border: 1px solid #ccc; border-radius: 6px; }
  .tk-consent-row { display: flex; gap: 8px; align-items: flex-start; margin-top: 10px; font-size: 13px; }
  .tk-consent-row input { width: auto; }
  .tk-error { color: #b00020; font-size: 13px; min-height: 16px; margin-top: 6px; }
  .tk-confirm { padding: 16px; text-align: center; }
`;

const SKELETON = `
  <button class="tk-bubble" type="button" aria-label="Open chat" aria-expanded="false" aria-controls="tk-panel">&#128172;</button>
  <section class="tk-panel" id="tk-panel" role="dialog" aria-label="Takshashila University chat" hidden>
    <header class="tk-header">
      <span class="tk-title">Takshashila University</span>
      <button class="tk-lead-btn" type="button">Talk to Admissions</button>
      <button class="tk-close" type="button" aria-label="Close chat">&#10005;</button>
    </header>
    <div class="tk-chat">
      <div class="tk-messages" role="log" aria-live="polite" aria-atomic="false"></div>
      <form class="tk-composer">
        <input class="tk-input" name="q" type="text" autocomplete="off" aria-label="Type your question" placeholder="Ask about admissions, fees, courses…" />
        <button class="tk-send" type="submit">Send</button>
      </form>
    </div>
    <div class="tk-lead" hidden></div>
  </section>
`;

const LEAD_FORM = `
  <form class="tk-lead-form">
    <label>Name<input name="name" type="text" autocomplete="name" /></label>
    <label>Email<input name="email" type="email" autocomplete="email" /></label>
    <label>Phone<input name="phone" type="tel" autocomplete="tel" /></label>
    <label>Program of interest (optional)<input name="program" type="text" /></label>
    <label>Message (optional)<textarea name="message" rows="2"></textarea></label>
    <div class="tk-consent-row">
      <input name="consent" type="checkbox" id="tk-consent" />
      <label for="tk-consent">I agree to be contacted by Admissions about my enquiry.</label>
    </div>
    <div class="tk-error" role="alert"></div>
    <button class="tk-send" type="submit">Send to Admissions</button>
  </form>
`;

export class Widget {
  readonly host: HTMLElement;
  readonly root: ShadowRoot;
  private readonly client: ChatClient;
  private readonly contact: Contact;
  private readonly sessionId: string;

  private readonly bubble: HTMLButtonElement;
  private readonly panel: HTMLElement;
  private readonly messages: HTMLElement;
  private readonly input: HTMLInputElement;
  private readonly chat: HTMLElement;
  private readonly leadView: HTMLElement;
  private readonly sendBtn: HTMLButtonElement;

  private lastDeadEndQuestion: string | null = null;
  private leadDeadEndQuestion: string | null = null;

  constructor(config: WidgetConfig) {
    this.client = config.client;
    this.contact = config.contact;
    this.sessionId = config.sessionId;

    this.host = document.createElement("div");
    this.root = this.host.attachShadow({ mode: "open" });
    this.root.innerHTML = `<style>${STYLE}</style>${SKELETON}`;
    document.body.appendChild(this.host);

    this.bubble = this.root.querySelector(".tk-bubble")!;
    this.panel = this.root.querySelector(".tk-panel")!;
    this.messages = this.root.querySelector(".tk-messages")!;
    this.input = this.root.querySelector(".tk-input")!;
    this.chat = this.root.querySelector(".tk-chat")!;
    this.leadView = this.root.querySelector(".tk-lead")!;
    this.sendBtn = this.root.querySelector(".tk-send")!;

    this.bubble.addEventListener("click", () => this.toggle());
    this.root.querySelector(".tk-close")!.addEventListener("click", () => this.close());
    this.root.querySelector(".tk-lead-btn")!.addEventListener("click", () => this.openLeadForm());
    this.root.querySelector(".tk-composer")!.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.send(this.input.value);
    });
    this.panel.addEventListener("keydown", (e) => {
      if ((e as KeyboardEvent).key === "Escape") this.close();
    });
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  open(): void {
    this.panel.hidden = false;
    this.bubble.setAttribute("aria-expanded", "true");
    this.input.focus();
  }

  close(): void {
    this.panel.hidden = true;
    this.bubble.setAttribute("aria-expanded", "false");
    this.bubble.focus();
  }

  toggle(): void {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  async send(raw: string): Promise<void> {
    const text = raw.trim();
    if (!text) return;

    this.showChat();
    this.addMessage("user", text);
    this.input.value = "";
    const bot = this.addMessage("bot", "");
    this.sendBtn.disabled = true;

    await this.client.streamChat(text, this.sessionId, {
      onToken: (token) => {
        bot.textContent += token;
        this.scrollToEnd();
      },
      onDone: (meta) => {
        this.sendBtn.disabled = false;
        if (meta.outcome === "dead_end") {
          this.lastDeadEndQuestion = text;
        }
        if (meta.offer_lead) {
          this.renderLeadOffer();
        }
      },
      onError: () => {
        this.sendBtn.disabled = false;
        bot.textContent = SOFT_FAIL;
        this.renderContact();
      },
    });
  }

  openLeadForm(deadEndQuestion: string | null = null): void {
    this.leadDeadEndQuestion = deadEndQuestion;
    this.chat.hidden = true;
    this.leadView.hidden = false;
    this.leadView.innerHTML = LEAD_FORM;
    this.leadView.querySelector(".tk-lead-form")!.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.submitLead();
    });
    (this.leadView.querySelector("[name=name]") as HTMLInputElement).focus();
  }

  async submitLead(): Promise<void> {
    const fields: LeadFields = {
      name: this.leadField("name").value,
      email: this.leadField("email").value,
      phone: this.leadField("phone").value,
      consent: (this.leadField("consent") as HTMLInputElement).checked,
      message: this.leadField("message").value,
    };

    const errors = validateLead(fields);
    if (errors.length) {
      this.setLeadError(errors.map((e) => e.message).join(" "));
      return;
    }

    const result = await this.client.submitLead({
      name: fields.name,
      email: fields.email,
      phone: fields.phone,
      program: this.leadField("program").value,
      message: fields.message,
      consent: fields.consent,
      dead_end_question: this.leadDeadEndQuestion,
      session_id: this.sessionId,
    });

    if (result.ok) {
      this.leadView.innerHTML = `<p class="tk-confirm">Thank you — the Admissions team will be in touch soon.</p>`;
      return;
    }

    const messages = (result.errors ?? []).map((e) => e.message).join(" ");
    this.setLeadError(messages || "Sorry, we couldn't submit that — please try again.");
  }

  private showChat(): void {
    this.leadView.hidden = true;
    this.chat.hidden = false;
  }

  private addMessage(role: "user" | "bot", text: string): HTMLElement {
    const el = document.createElement("div");
    el.className = `tk-msg tk-msg-${role}`;
    el.textContent = text;
    this.messages.appendChild(el);
    this.scrollToEnd();
    return el;
  }

  private renderLeadOffer(): void {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tk-lead-offer";
    button.textContent = "Talk to Admissions";
    button.addEventListener("click", () => this.openLeadForm(this.lastDeadEndQuestion));
    this.messages.appendChild(button);
    this.scrollToEnd();
  }

  private renderContact(): void {
    const el = document.createElement("div");
    el.className = "tk-contact";
    el.textContent = `Email: ${this.contact.email} · Phone: ${this.contact.phone} · ${this.contact.page}`;
    this.messages.appendChild(el);
  }

  private leadField(name: string): HTMLInputElement {
    return this.leadView.querySelector(`[name=${name}]`) as HTMLInputElement;
  }

  private setLeadError(message: string): void {
    (this.leadView.querySelector(".tk-error") as HTMLElement).textContent = message;
  }

  private scrollToEnd(): void {
    this.messages.scrollTop = this.messages.scrollHeight;
  }
}
