import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../src/lib/chat-history.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2017 },
});
const { buildChatHistory } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("retains earlier business context and current semantic state", () => {
  const messages = [{ role: "user", content: "Somos una clínica de rehabilitación." }];
  messages.push(...Array.from({ length: 30 }, () => ({ role: "assistant", content: "x".repeat(10_000) })));
  messages.push({ role: "assistant", content: "Entidad elegida.", semanticContext: { primary_measure: "Metrics.recovery" } });
  const history = buildChatHistory(messages);
  assert.equal(history[0].content, messages[0].content);
  assert.deepEqual(history.at(-1).semantic_context, messages.at(-1).semanticContext);
  assert.ok(history.reduce((size, message) => size + message.content.length, 0) <= 48_000);
  assert.ok(history.every((message) => message.content.length <= 6_000));
});

test("does not send loading or failed responses as business context", () => {
  assert.deepEqual(buildChatHistory([
    { role: "assistant", content: "Respuesta parcial", isLoading: true },
    { role: "assistant", content: "Error: conexión" },
    { role: "user", content: "Vendemos maquinaria." },
  ]), [{ role: "user", content: "Vendemos maquinaria.", semantic_context: undefined }]);
});

test("keeps latest structured scope through a long conceptual detour", () => {
  const state = { connection_id: "c", catalog_fingerprint: "revision", primary_measure: "Model.rate" };
  const messages = Array.from({ length: 8 }, () => ({ role: "user", content: "x".repeat(6_000) }));
  messages.push({ role: "assistant", content: "Alcance seleccionado", semanticContext: state });
  messages.push(...Array.from({ length: 10 }, () => ({ role: "assistant", content: "y".repeat(6_000) })));
  const history = buildChatHistory(messages);
  assert.ok(history.some((message) => message.semantic_context?.catalog_fingerprint === "revision"));
  assert.ok(history.reduce((size, message) => size + message.content.length, 0) <= 48_000);
});

test("retains a later correction before a full original context under pressure", () => {
  const original = { role: "user", content: ("El contexto inicial es X. " + "x".repeat(6_000)).slice(0, 6_000) };
  const correction = { role: "user", content: "Corrección: el contexto vigente es Y." };
  const messages = [original, ...Array.from({ length: 7 }, () => ({ role: "assistant", content: "a".repeat(6_000) })),
    correction, ...Array.from({ length: 12 }, () => ({ role: "user", content: "b".repeat(6_000) }))];
  const history = buildChatHistory(messages);
  assert.ok(history.some((message) => message.content === correction.content));
  assert.equal(history.at(-1).content, messages.at(-1).content);
  assert.ok(history.reduce((size, message) => size + message.content.length, 0) <= 48_000);
});

test("preserves corrections from multiple business domains", () => {
  const corrections = [
    { role: "user", content: "Corrijo: en salud contamos sesiones, no pacientes." },
    { role: "user", content: "En realidad el negocio industrial tiene dos plantas." },
  ];
  const history = buildChatHistory([
    ...Array.from({ length: 8 }, () => ({ role: "user", content: "x".repeat(6_000) })), ...corrections,
    ...Array.from({ length: 10 }, () => ({ role: "assistant", content: "y".repeat(6_000) })),
  ]);
  for (const correction of corrections) assert.ok(history.some((message) => message.content === correction.content));
});

test("preserves the head and final correction while disclosing truncation", () => {
  const content = "Contexto inicial. " + "x".repeat(7_000) + " Corrección final: el negocio ahora es Y.";
  const history = buildChatHistory([{ role: "user", content }]);
  assert.ok(history[0].content.startsWith("Contexto inicial."));
  assert.ok(history[0].content.endsWith("Corrección final: el negocio ahora es Y."));
  assert.ok(history[0].content.includes("[Mensaje truncado:"));
  assert.equal(history[0].content.length, 6_000);
});

test("keeps an explicit reset with empty query after a long detour", () => {
  const state = { version: 3, scope_reset: true, query: {}, selected_entities: [] };
  const history = buildChatHistory([
    { role: "assistant", content: "Listo.", semanticContext: state },
    ...Array.from({ length: 10 }, () => ({ role: "assistant", content: "x".repeat(6_000) })),
  ]);
  assert.ok(history.some((message) => message.semantic_context?.scope_reset === true));
  assert.ok(history.reduce((size, message) => size + message.content.length, 0) <= 48_000);
});

test("retains a state-only reset with opaque keys and an empty message", () => {
  const reset = { version: 3, scope_reset: true, connection_id: "c", query: {}, selected_entities: [] };
  const history = buildChatHistory([
    { role: "assistant", content: "Antes", semanticContext: {
      query: { measures: ["Q17.k03"], filters: [{ member: "R21.k08", values: ["A"] }] },
    } },
    { role: "assistant", content: "", semanticContext: reset },
    ...Array.from({ length: 12 }, () => ({ role: "user", content: "x".repeat(6_000) })),
  ]);
  assert.deepEqual(history.filter((message) => message.semantic_context).at(-1), {
    role: "assistant", content: "", semantic_context: reset,
  });
  assert.ok(history.reduce((size, message) => size + message.content.length, 0) <= 48_000);
});
