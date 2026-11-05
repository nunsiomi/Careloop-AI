// Railway setup for CareLoop (replaces railway.json and voice/railway.json).
// Variables are not kept here: set them in Railway (careloop → service → Variables). Postgres was added in Railway
// and is left to it; this file only manages the two services below.
import { defineRailway, github, project, service } from "railway/iac";

export const partial = "careloop";

export default defineRailway(() => {
  // FastAPI backend, serving the patient app and dashboard on the same address (Dockerfile at the repo root).
  const api = service("careloop-api", {
    source: github("nunsiomi/Careloop-AI"),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["backend/**", "frontend/**", "data/**", "voice/prompts/**", "Dockerfile"] },
    healthcheck: "/api/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
  });

  // Tomi's LiveKit worker (voice/Dockerfile). It has no web address; LiveKit sends it the calls.
  const tomi = service("tomi-voice", {
    source: github("nunsiomi/Careloop-AI", { rootDirectory: "voice" }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["voice/**"] },
    replicas: { "sfo": 1 },
  });

  return project("careloop", {
    variables: { managed: false },
    resources: [api, tomi],
  });
});
