import { waitFor } from "./utils/service-utils";

export default async () => {
  console.log("Waiting for backend to be ready...");
  await waitFor("http://localhost:8000/health", 30, 1000);
  console.log("Backend is ready!");

  console.log("Waiting for frontend to be ready...");
  await waitFor("http://localhost:3000/login", 30, 1000);
  console.log("Frontend is ready!");
};
