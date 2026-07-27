import type { PipelineDeps } from "../pipeline";
import { classifyQuestion, generateAnswer } from "./llm";

/** The real (OpenAI-backed) pipeline dependencies used by the /api/ask route. */
export const realDeps: PipelineDeps = {
  classify: classifyQuestion,
  generate: generateAnswer,
};
