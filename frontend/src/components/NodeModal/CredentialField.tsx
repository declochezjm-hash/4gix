import { useCallback, useEffect, useState } from "react";
import {
	createCredential,
	fetchCredentials,
	type CredentialSummary,
} from "../../lib/api";

type CredentialFieldProps = {
	title: string;
	description?: string;
	credentialType: string;
	value: unknown;
	onChange: (credentialId: string) => void;
};

export function CredentialField({
	title,
	description,
	credentialType,
	value,
	onChange,
}: CredentialFieldProps) {
	const [items, setItems] = useState<CredentialSummary[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [creating, setCreating] = useState(false);
	const [newName, setNewName] = useState("");

	const reload = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const rows = await fetchCredentials(credentialType);
			setItems(rows);
		} catch {
			setError("Impossible de charger les credentials.");
			setItems([]);
		} finally {
			setLoading(false);
		}
	}, [credentialType]);

	useEffect(() => {
		void reload();
	}, [reload]);

	const current = String(value ?? "");

	async function handleCreate() {
		const name = newName.trim();
		if (!name) return;
		setCreating(true);
		setError(null);
		try {
			const created = await createCredential({
				name,
				type: credentialType,
			});
			setNewName("");
			await reload();
			onChange(created.id);
		} catch {
			setError("Création du credential impossible.");
		} finally {
			setCreating(false);
		}
	}

	return (
		<div className="credential-field">
			<label>
				{title}
				{description ? <small>{description}</small> : null}
				<select
					value={current}
					disabled={loading}
					onChange={(e) => onChange(e.target.value)}
				>
					<option value="">
						{loading ? "Chargement…" : "— Sélectionner un credential —"}
					</option>
					{items.map((item) => (
						<option key={item.id} value={item.id}>
							{item.name}
						</option>
					))}
				</select>
			</label>
			<div className="credential-field__create">
				<input
					type="text"
					placeholder="Nouveau credential…"
					value={newName}
					onChange={(e) => setNewName(e.target.value)}
					disabled={creating}
				/>
				<button
					type="button"
					className="ghost-btn"
					disabled={creating || !newName.trim()}
					onClick={() => void handleCreate()}
				>
					Créer
				</button>
			</div>
			{error ? <small className="credential-field__error">{error}</small> : null}
		</div>
	);
}
