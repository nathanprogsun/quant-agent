"use client";

import { useEffect, useState } from "react";

import { listSkills } from "./api";
import type { SkillDisclosure } from "./types";

export interface UseSkillsResult {
  skills: SkillDisclosure[];
  loading: boolean;
  error: Error | null;
  reload: () => Promise<void>;
}

export function useSkills(): UseSkillsResult {
  const [skills, setSkills] = useState<SkillDisclosure[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const reload = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const result = await listSkills();
      setSkills(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setSkills([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  return { skills, loading, error, reload };
}
