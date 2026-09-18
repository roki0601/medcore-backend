export default function projectProviders(pi: {
  registerProvider: (name: string, config: Record<string, unknown>) => void;
}) {
  // The corporate Qwen service is exposed locally by the user's tunnel.
  // This override is loaded only by the project wrapper and never edits ~/.omp.
  pi.registerProvider("ufanet-local", {
    baseUrl: "http://127.0.0.1:8055/v1",
    api: "openai-completions",
    auth: "none",
    // OMP's runtime registration schema requires a non-empty apiKey field;
    // auth:none prevents this placeholder from being sent to the local service.
    apiKey: "UFANET_LOCAL_API_KEY",
    models: [
      {
        id: "Qwen3-Coder-Next-NVFP4",
        name: "Ufanet Qwen3 Coder (project tunnel)",
        input: ["text"],
        contextWindow: 128000,
        maxTokens: 16384,
        reasoning: true,
        cost: {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
        },
      },
    ],
  });
}
