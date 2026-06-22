// Streaming Server-Sent-Events parser for the /chat response.
// Mirrors the backend's `data: {json}\n\n` framing and tolerates chunk splits.

export type SSEEvent =
  | { type: "token"; text: string }
  | {
      type: "done";
      outcome: string;
      offer_lead?: boolean;
      language?: string | null;
      citations?: string[];
    };

export function createSSEParser(onEvent: (event: SSEEvent) => void): (chunk: string) => void {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    let index: number;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 2);
      if (block.startsWith("data:")) {
        onEvent(JSON.parse(block.slice(5).trim()) as SSEEvent);
      }
    }
  };
}
