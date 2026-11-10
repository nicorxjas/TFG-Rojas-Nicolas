import type { Skill } from "@/app/skills/types";

export interface Agent {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  category?: string;
  iconType?: "icon" | "emoji";
  iconName?: string;
  iconColor?: string;
  iconEmoji?: string;
  skills?: Skill[];
  createdAt: string;
}
