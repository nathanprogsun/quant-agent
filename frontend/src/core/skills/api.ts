import type { SkillDisclosure } from "./types";

const BASE_URL = "/api/skills";

export async function listSkills(): Promise<SkillDisclosure[]> {
  const response = await fetch(`${BASE_URL}/disclosure`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch skills (status ${response.status})`);
  }

  const data = (await response.json()) as { skills: SkillDisclosure[] };
  return data.skills ?? [];
}

export async function setSkillEnabled(
  name: string,
  enabled: boolean,
): Promise<SkillDisclosure> {
  const response = await fetch(`${BASE_URL}/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ enabled }),
  });

  if (!response.ok) {
    throw new Error(`Failed to toggle skill ${name} (status ${response.status})`);
  }

  return (await response.json()) as SkillDisclosure;
}
