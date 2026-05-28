const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const TEST_USER = {
  email: "e2e-test@example.com",
  password: "TestPassword123!",
  full_name: "E2E Test User",
};

async function globalSetup(): Promise<void> {
  console.log("Starting global E2E setup...");

  // Wait for backend to be ready
  await waitForBackend();

  // Register test user
  await registerTestUser();

  console.log("Global E2E setup complete");
}

async function waitForBackend(maxRetries = 30, delayMs = 1000): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(`${BACKEND_URL}/health`);
      if (response.ok) {
        console.log("Backend is ready");
        return;
      }
    } catch {
      // Backend not ready yet
    }
    console.log(`Waiting for backend... (${i + 1}/${maxRetries})`);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw new Error("Backend did not become ready in time");
}

async function registerTestUser(): Promise<void> {
  console.log("Registering test user...");

  const response = await fetch(`${BACKEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(TEST_USER),
  });

  if (response.status === 201 || response.status === 200) {
    console.log("Test user registered successfully");
  } else if (response.status === 409) {
    console.log("Test user already exists, continuing...");
  } else {
    const text = await response.text();
    console.error(`Failed to register test user: ${response.status} ${text}`);
    throw new Error(`Failed to register test user: ${response.status}`);
  }
}

export default globalSetup;
