import type { SkillDisclosure } from "./types";

const MAX_SUGGESTIONS = 5;

/**
 * Match skill suggestions for a slash-command prefix.
 *
 * Returns enabled skills whose name starts with the prefix (case-insensitive),
 * excluding reserved names. The prefix is the text after the leading `/`.
 * Returns an empty array when the prefix is empty or no skills match.
 */
export function getMatchingSkillSuggestions(
  prefix: string,
  skills: SkillDisclosure[],
  options: { max?: number } = {},
): SkillDisclosure[] {
  const limit = options.max ?? MAX_SUGGESTIONS;
  const normalized = prefix.trim().toLowerCase();

  const candidates = skills
    .filter((skill) => skill.enabled)
    .filter((skill) => !RESERVED_SKILL_NAMES.has(skill.name));

  // Empty prefix (slash just typed) → show all enabled non-reserved skills.
  if (!normalized) return candidates.slice(0, limit);

  return candidates
    .filter((skill) => skill.name.toLowerCase().startsWith(normalized))
    .slice(0, limit);
}

/**
 * Apply a chosen skill suggestion to the input text.
 *
 * Replaces the trailing `/<prefix>` token with `/<name> ` (literal slash-name
 * followed by a space) so the user can continue typing arguments.
 */
export function applySkillSuggestion(
  input: string,
  name: string,
): string {
  const slashIndex = input.lastIndexOf("/");
  if (slashIndex === -1) return input;
  return `${input.slice(0, slashIndex)}/${name} `;
}

export const RESERVED_SKILL_NAMES: ReadonlySet<string> = new Set([
  "bootstrap",
  "help",
  "memory",
  "models",
  "new",
  "status",
]);
