export interface Actionable {
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  text: string;
}

export interface ReportContent {
  executive_summary: string;
  actionables?: Actionable[];
}

export interface ReportAgent {
  id: string;
  name: string;
  description?: string | null;
  system_prompt?: string | null;
  systemPrompt?: string;
  category?: string | null;
  icon_type?: "icon" | "emoji" | null;
  iconType?: "icon" | "emoji";
  icon_name?: string | null;
  iconName?: string;
  icon_color?: string | null;
  iconColor?: string;
  icon_emoji?: string | null;
  iconEmoji?: string;
  created_at?: string | null;
  createdAt?: string;
}

export interface Report {
  id: string;
  template_id: string | null;
  user_id: string;
  status: 'PENDING' | 'GENERATING' | 'SUCCESS' | 'FAILED';
  content: ReportContent | null;
  error_log: string | null;
  created_at: string;
  updated_at: string;
  name: string;
  prompt?: string | null;
  include_charts?: boolean;
  semantic_connection_id?: string | null;
  report_agents?: { agents: ReportAgent | null }[];
}
