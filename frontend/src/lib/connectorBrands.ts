/** Couleurs d'accent type n8n pour les connecteurs HITL. */
export const CONNECTOR_ACCENT: Record<string, string> = {
	connector_discord: "#5865F2",
	connector_gmail: "#EA4335",
	connector_google_chat: "#34A853",
	connector_microsoft_outlook: "#0078D4",
	connector_microsoft_teams: "#6264A7",
	connector_send_email: "#14B8A6",
	connector_slack: "#E01E5A",
	connector_telegram: "#229ED9",
	connector_whatsapp: "#25D366",
	human_approval: "#EC4899",
};

export function accentForNode(nodeType: string, fallback: string): string {
	return CONNECTOR_ACCENT[nodeType] || fallback;
}
