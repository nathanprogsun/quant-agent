export async function waitFor(
  url: string,
  maxAttempts: number = 30,
  delay: number = 1000
): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, delay));
  }
  throw new Error(`Service at ${url} did not become ready`);
}
