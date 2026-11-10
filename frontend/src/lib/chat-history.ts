type HistoryMessage = {
  role: string;
  content: string;
  isLoading?: boolean;
  semanticContext?: Record<string, unknown>;
};

const HISTORY_BUDGET = 48_000;
const MESSAGE_BUDGET = 6_000;
const TRUNCATION_MARKER = "\n[Mensaje truncado: se omitió parte del contenido intermedio.]\n";
const CORRECTION_PATTERN = /\b(?:correccion|corrijo|rectifico|quise decir|me equivoque|en realidad|desde ahora|a partir de ahora|olvida|olvidate|no uses|en lugar de|reemplaza|reemplazar|sustitui|sustituye)\b/;

function normalizedText(content: string) {
  return content.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function boundedContent(content: string) {
  if (content.length <= MESSAGE_BUDGET) return content;
  const available = MESSAGE_BUDGET - TRUNCATION_MARKER.length;
  const head = Math.ceil(available / 2);
  const tail = available - head;
  return content.slice(0, head) + TRUNCATION_MARKER + content.slice(-tail);
}

// Retain explicit corrections before old context, and disclose any truncation.
export function buildChatHistory(messages: HistoryMessage[]) {
  const valid = messages.filter((message) =>
    !message.isLoading && (message.content || message.semanticContext)
    && !message.content.startsWith("Error:")
  );
  const indices = valid.map((_, index) => index);
  const priority = [
    ...indices.filter((index) => valid[index].semanticContext).slice(-1),
    ...indices.slice(-6).reverse(),
    ...indices.filter((index) => valid[index].role === "user"
      && CORRECTION_PATTERN.test(normalizedText(valid[index].content))).reverse(),
    ...indices.slice(0, 6),
    ...indices.filter((index) => valid[index].role === "user").reverse(),
    ...[...indices].reverse(),
  ];
  const selected = new Set<number>();
  let remaining = HISTORY_BUDGET;
  for (const index of priority) {
    const size = Math.min(valid[index].content.length, MESSAGE_BUDGET);
    if (!selected.has(index) && size <= remaining) {
      selected.add(index);
      remaining -= size;
    }
  }
  return indices.filter((index) => selected.has(index)).map((index) => ({
    role: valid[index].role,
    content: boundedContent(valid[index].content),
    semantic_context: valid[index].semanticContext,
  }));
}
