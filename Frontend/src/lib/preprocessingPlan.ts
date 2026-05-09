/**
 * Normalise preprocessing plan payloads into a consistent shape for display.
 *
 * The LLM can return the plan in several formats:
 *  (a) Array of objects  { step, action, columns, reason }
 *  (b) One big string    "1_flag_columns— …description… 2_next— …"
 *  (c) Array of strings  (each possibly being the concatenated blob above)
 */

export interface NormalizedPlanStep {
  index: number;
  title: string;
  detail: string;
  columns?: string[];
}

/** Convert a snake_case slug into a readable title (strips leading digit). */
export function humanizeSlug(slug: string): string {
  return slug
    .replace(/^[0-9]+_/, "")      // strip leading number
    .replace(/_/g, " ")            // underscores → spaces
    .replace(/\b\w/g, (c) => c.toUpperCase()); // title-case
}

/**
 * Split a concatenated LLM blob like:
 *   "1_flag_columns— description… 2_next_step— description…"
 * into individual steps.
 */
export function parseConcatenatedBlob(text: string): NormalizedPlanStep[] {
  const trimmed = text.trim();
  if (!trimmed) return [];

  // Match patterns: "1_some_slug— " or "1_some_slug - "
  const headerRe = /(\d+)_([a-z][a-z0-9_]*)\s*[\u2014\u2013\-]+\s*/gi;

  const hits: Array<{
    order: number;
    slug: string;
    bodyStart: number;
    headerIndex: number;
  }> = [];

  let m: RegExpExecArray | null;
  while ((m = headerRe.exec(trimmed)) !== null) {
    hits.push({
      order: parseInt(m[1], 10),
      slug: m[2],
      headerIndex: m.index,
      bodyStart: m.index + m[0].length,
    });
  }

  if (hits.length === 0) return [];

  return hits.map((hit, i) => {
    const end = i + 1 < hits.length ? hits[i + 1].headerIndex : trimmed.length;
    return {
      index: hit.order,
      title: humanizeSlug(hit.slug),
      detail: trimmed.slice(hit.bodyStart, end).trim(),
    };
  });
}

/** How many concatenated-blob headers are in a string? */
function countBlobHeaders(text: string): number {
  return (text.match(/\d+_[a-z][a-z0-9_]*\s*[\u2014\u2013\-]+/gi) ?? []).length;
}

function parseColumns(o: Record<string, unknown>): string[] | undefined {
  const v = o["columns"];
  if (Array.isArray(v)) return v.map(String).filter(Boolean);
  if (typeof v === "string" && v.trim()) return [v.trim()];
  return undefined;
}

/**
 * Main entry point: accepts the raw `preprocessing_plan` object from the API
 * and returns a clean array of steps for display.
 */
export function normalizePreprocessingPlanSteps(
  plan: Record<string, unknown> | null
): NormalizedPlanStep[] {
  if (!plan) return [];

  // Check if the plan itself is a concatenated blob stored under a string key
  for (const key of ["preprocessing_steps", "steps"] as const) {
    const v = plan[key];
    if (typeof v === "string") {
      const parsed = parseConcatenatedBlob(v);
      if (parsed.length > 0) return parsed;
    }
  }

  const raw = plan["preprocessing_steps"] ?? plan["steps"];
  if (!Array.isArray(raw) || raw.length === 0) return [];

  const out: NormalizedPlanStep[] = [];

  for (let i = 0; i < raw.length; i++) {
    const item = raw[i];

    // Plain string element
    if (typeof item === "string") {
      const parsed = parseConcatenatedBlob(item);
      if (parsed.length > 0) {
        out.push(...parsed);
      } else {
        out.push({ index: out.length + 1, title: `Step ${out.length + 1}`, detail: item });
      }
      continue;
    }

    if (!item || typeof item !== "object") continue;

    const o = item as Record<string, unknown>;
    const step   = String(o["step"]   ?? "").trim();
    const action = String(o["action"] ?? "").trim();
    const reason = String(o["reason"] ?? o["justification"] ?? "").trim();

    // If step + reason together look like a blob, split it
    const combined = [step, reason].filter(Boolean).join(" ");
    if (countBlobHeaders(combined) >= 2) {
      out.push(...parseConcatenatedBlob(combined));
      continue;
    }

    // Normal structured object
    const slugMatch = /^(\d+)_([a-z][a-z0-9_]*)$/i.exec(step);
    const title = slugMatch
      ? humanizeSlug(slugMatch[0])
      : step || action || `Step ${i + 1}`;

    const detail =
      reason ||
      (action && action !== step ? action : "") ||
      "";

    const cols = parseColumns(o);

    out.push({
      index: slugMatch ? parseInt(slugMatch[1], 10) : i + 1,
      title,
      detail: detail.trim(),
      ...(cols?.length ? { columns: cols } : {}),
    });
  }

  return out;
}
