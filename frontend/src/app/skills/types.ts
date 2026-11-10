import type { Agent } from "@/app/agentes/types";

export interface Skill {
  id: string;
  name: string;
  description: string;
  instruction: string;
  agents: Agent[];
  createdAt: string;
  updatedAt?: string;
}
