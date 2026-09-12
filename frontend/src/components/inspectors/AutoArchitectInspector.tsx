import type { Edge, Node } from "@xyflow/react";
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
	FlowNodeData,
	StepArchitectPreviousStep,
	StepArchitectResult,
} from "../../lib/api";
import { stepArchitectAgent } from "../../lib/api";
import {
	applyArchitectSequentialLayout,
	ghostNodeFromArchitectPayload,
	graphForStepArchitectRequest,
	resolveArchitectLayoutAnchorId,
	resolveUpstreamDataSourceId,
} from "../../lib/composerCanvas";
import { useComposerAgentContext } from "../agent/ComposerAgentContext";
import { useDagStore } from "../../store/dagStore";

export type ArchitectChatMessage = {
	role: "user" | "assistant" | "system";
	content: string;
	at: string;
};

function parseArchitectChat(raw: unknown): ArchitectChatMessage[] {
	if (!Array.isArray(raw)) return [];
	return raw.filter(
		(item): item is ArchitectChatMessage =>
			typeof item === "object" &&
			item !== null &&
			typeof (item as ArchitectChatMessage).content === "string",
	);
}

/** Reader en amont (arêtes) pour l'API step-architect (inspect schéma). */
function resolveSourceNodeId(
	nodes: Node<FlowNodeData>[],
	edges: Edge[],
	targetNodeId: string,
	explicitSourceId: string | null,
): string | null {
	if (explicitSourceId?.trim()) return explicitSourceId.trim();
	const upstream = resolveUpstreamDataSourceId(nodes, edges, targetNodeId);
	if (upstream) return upstream;
	const parentEdge = edges.find((edge) => edge.target === targetNodeId);
	return parentEdge?.source ?? null;
}

function errorMessage(err: unknown): string {
	if (err instanceof Error) return err.message;
	return "Échec de l'appel au serveur.";
}

export function AutoArchitectInspector({ nodeId }: { nodeId: string }) {
	const nodes = useDagStore((s) => s.nodes);
	const edges = useDagStore((s) => s.edges);
	const updateNodeParams = useDagStore((s) => s.updateNodeParams);
	const setStepProposals = useDagStore((s) => s.setStepProposals);
	const discardStoreProposals = useDagStore((s) => s.discardProposals);
	const setArchitectGenerating = useDagStore((s) => s.setArchitectGenerating);
	const setArchitectSession = useDagStore((s) => s.setArchitectSession);
	const appendStepProposals = useDagStore((s) => s.appendStepProposals);
	const stepProposalNodes = useDagStore((s) => s.stepProposalNodes);
	const architectGlobalPlan = useDagStore((s) => s.architectGlobalPlan);
	const architectStepIndex = useDagStore((s) => s.architectStepIndex);
	const architectTotalSteps = useDagStore((s) => s.architectTotalSteps);
	const architectPreviousSteps = useDagStore((s) => s.architectPreviousSteps);
	const architectSourceNodeId = useDagStore((s) => s.architectSourceNodeId);
	const architectGlobalObjective = useDagStore((s) => s.architectGlobalObjective);

	const { setProposedNodes, setProposedEdges, rejectAll, setAgentMode } =
		useComposerAgentContext();

	const node = nodes.find((item) => item.id === nodeId);
	const storedObjective =
		typeof node?.data.params?.global_objective === "string"
			? node.data.params.global_objective
			: "";
	const chatHistory = parseArchitectChat(node?.data.params?.architect_chat_history);

	const [autoAdvance, setAutoAdvance] = useState<boolean>(
		node?.data.params?.auto_advance !== false,
	);
	const [promptText, setPromptText] = useState(
		storedObjective || architectGlobalObjective,
	);
	const [thinkingOpen, setThinkingOpen] = useState(true);
	const [thinkingLog, setThinkingLog] = useState<string[]>([]);
	const [isLoading, setIsLoading] = useState(false);
	const [inspectorError, setInspectorError] = useState<string | null>(null);
	const inFlightRef = useRef(false);
	const autoAdvanceRef = useRef(autoAdvance);
	autoAdvanceRef.current = autoAdvance;

	useEffect(() => {
		setPromptText(storedObjective || architectGlobalObjective);
	}, [storedObjective, architectGlobalObjective]);

	useEffect(() => {
		if (node?.data.params?.auto_advance === undefined) return;
		setAutoAdvance(node.data.params.auto_advance !== false);
	}, [node?.data.params?.auto_advance, nodeId]);

	useEffect(() => {
		setAgentMode("step");
	}, [setAgentMode]);

	const dataSourceId = useMemo(
		() =>
			resolveSourceNodeId(nodes, edges, nodeId, architectSourceNodeId),
		[nodes, edges, nodeId, architectSourceNodeId],
	);

	const hasProposals = stepProposalNodes.length > 0;
	const isGenerating = isLoading;
	const globalPlan = architectGlobalPlan;
	const totalSteps = architectTotalSteps || globalPlan.length;
	const currentStepIndex = architectStepIndex;

	const pushThinking = useCallback((line: string) => {
		setThinkingLog((prev) => [...prev, line]);
	}, []);

	const beginLoading = useCallback(() => {
		setIsLoading(true);
		setInspectorError(null);
		setArchitectGenerating(true);
	}, [setArchitectGenerating]);

	const endLoading = useCallback(() => {
		setIsLoading(false);
		setArchitectGenerating(false);
	}, [setArchitectGenerating]);

	const syncProposals = useCallback(
		(proposedNodes: Node<FlowNodeData>[], proposedEdges: Edge[]) => {
			setStepProposals(proposedNodes, proposedEdges);
			setProposedNodes([]);
			setProposedEdges([]);
		},
		[setProposedEdges, setProposedNodes, setStepProposals],
	);

	const appendChat = (...messages: ArchitectChatMessage[]) => {
		const current = useDagStore
			.getState()
			.nodes.find((item) => item.id === nodeId);
		const hist = parseArchitectChat(
			current?.data.params?.architect_chat_history,
		);
		updateNodeParams(nodeId, {
			architect_chat_history: [...hist, ...messages],
		});
	};

	const reportError = useCallback(
		(message: string) => {
			setInspectorError(message);
			pushThinking(message);
			useDagStore.setState({ error: message });
			console.error("Erreur Step Architect:", message);
		},
		[pushThinking],
	);

	const runArchitectPipeline = useCallback(
		async (
			objective: string,
			dataSourceId: string,
			options: {
				/** Enchaîner les appels jusqu'à la fin du plan (prévisualisation A→B→C). */
				continueUntilComplete: boolean;
				materialize: boolean;
				initialPreviousSteps?: StepArchitectPreviousStep[];
				initialStepIndex?: number;
				layoutStartNodeId?: string;
			},
		) => {
			const canvasNodes = useDagStore.getState().nodes;
			let lastNodeId = resolveArchitectLayoutAnchorId(
				canvasNodes,
				options.layoutStartNodeId ?? nodeId,
			);
			const ghostNodesAcc: Node<FlowNodeData>[] = [];
			const ghostEdgesAcc: Edge[] = [];
			let previousSteps = options.initialPreviousSteps ?? [];
			let stepIndex = options.initialStepIndex ?? 0;
			let total = 8;
			let firstResult: StepArchitectResult | null = null;

			while (stepIndex < total) {
				const state = useDagStore.getState();
				const result = await stepArchitectAgent({
					global_objective: objective,
					current_step_index: stepIndex,
					previous_steps: previousSteps,
					current_graph: graphForStepArchitectRequest(
						state.nodes,
						state.edges,
						state.snapshots,
						ghostNodesAcc,
						ghostEdgesAcc,
					),
					source_node_id: dataSourceId,
					layout_anchor_node_id: lastNodeId,
				});

				if (!firstResult) firstResult = result;
				setArchitectSession({
					globalPlan: result.global_plan || [],
					stepIndex: result.current_step_index ?? stepIndex,
					totalSteps: result.total_steps ?? result.global_plan?.length ?? 0,
					previousSteps,
					sourceNodeId: dataSourceId,
					globalObjective: objective,
				});
				if (result.step_summary) {
					pushThinking(`Étape ${stepIndex + 1} : ${result.step_summary}`);
				}

				if (!result.proposed_node) break;

				const rawNode = ghostNodeFromArchitectPayload(
					result.proposed_node as Record<string, unknown>,
				);
				const layoutAnchorId = resolveArchitectLayoutAnchorId(
					[...state.nodes, ...ghostNodesAcc],
					lastNodeId,
				);
				const laid = applyArchitectSequentialLayout(
					[...state.nodes, ...ghostNodesAcc],
					[...state.edges, ...ghostEdgesAcc],
					layoutAnchorId,
					rawNode,
					ghostEdgesAcc,
				);
				ghostNodesAcc.push(laid.node);
				if (laid.edge) ghostEdgesAcc.push(laid.edge);
				lastNodeId = laid.node.id;

				previousSteps = [
					...previousSteps,
					{
						index: stepIndex,
						node_id: laid.node.id,
						step_summary:
							result.step_summary ||
							result.global_plan?.[stepIndex] ||
							`Étape ${stepIndex + 1}`,
					},
				];
				stepIndex += 1;
				total = result.total_steps ?? total;

				syncProposals(ghostNodesAcc, ghostEdgesAcc);
				setArchitectSession({
					previousSteps,
					stepIndex,
					totalSteps: total,
				});

				if (result.is_complete || stepIndex >= total) break;
				if (!options.continueUntilComplete) break;
			}

			if (options.materialize && ghostNodesAcc.length) {
				appendStepProposals(ghostNodesAcc, ghostEdgesAcc);
				discardStoreProposals();
				rejectAll();
			}

			return { firstResult, ghostNodesAcc, ghostEdgesAcc, stepIndex, total };
		},
		[
			appendStepProposals,
			discardStoreProposals,
			nodeId,
			pushThinking,
			rejectAll,
			setArchitectSession,
			syncProposals,
		],
	);

	const handleApplyAll = useCallback(
		async (options?: { parentLoading?: boolean }) => {
			const ownsLoading = !options?.parentLoading;
			if (ownsLoading) {
				if (inFlightRef.current) return;
				inFlightRef.current = true;
				beginLoading();
			}

			const objective = architectGlobalObjective || promptText.trim();
			const sourceId = resolveSourceNodeId(
				useDagStore.getState().nodes,
				useDagStore.getState().edges,
				nodeId,
				architectSourceNodeId,
			);

			if (!objective || !sourceId) {
				const msg = !sourceId
					? "Aucune source détectée : reliez un reader au nœud Auto-Architect (ou placez un reader sur le canvas)."
					: "Saisissez un objectif global avant d’appliquer le pipeline.";
				reportError(`Erreur : ${msg}`);
				if (ownsLoading) {
					inFlightRef.current = false;
					endLoading();
				}
				return;
			}

			if (ownsLoading) {
				pushThinking("Consolidation du pipeline sur le canvas…");
			}

			try {
				let layoutStartNodeId = nodeId;
				let stepIndex = architectStepIndex;
				let previousSteps = [...architectPreviousSteps];

				if (useDagStore.getState().stepProposalNodes.length) {
					const ghostNodes = useDagStore.getState().stepProposalNodes;
					const ghostEdges = useDagStore.getState().stepProposalEdges;
					appendStepProposals(ghostNodes, ghostEdges);
					discardStoreProposals();
					rejectAll();
					const materializedId = ghostNodes[ghostNodes.length - 1]?.id;
					if (materializedId) {
						layoutStartNodeId = materializedId;
						previousSteps = [
							...previousSteps,
							{
								index: stepIndex,
								node_id: materializedId,
								step_summary:
									globalPlan[stepIndex] || `Étape ${stepIndex + 1}`,
							},
						];
						stepIndex += 1;
						setArchitectSession({
							previousSteps,
							stepIndex,
						});
					}
				}

				await runArchitectPipeline(objective, sourceId, {
					continueUntilComplete: true,
					materialize: true,
					initialPreviousSteps: previousSteps,
					initialStepIndex: stepIndex,
					layoutStartNodeId,
				});

				discardStoreProposals();
				rejectAll();
				pushThinking("Pipeline appliqué sur le canvas.");
				useDagStore.setState({
					inspectorOpen: false,
					importNotice: "Pipeline consolidé sur le canvas.",
					error: null,
				});
			} catch (err) {
				reportError(errorMessage(err));
			} finally {
				if (ownsLoading) {
					inFlightRef.current = false;
					endLoading();
				}
			}
		},
		[
			architectGlobalObjective,
			architectPreviousSteps,
			architectSourceNodeId,
			architectStepIndex,
			architectTotalSteps,
			appendStepProposals,
			beginLoading,
			discardStoreProposals,
			endLoading,
			globalPlan,
			nodeId,
			runArchitectPipeline,
			promptText,
			pushThinking,
			rejectAll,
			reportError,
			setArchitectSession,
		],
	);

	const handleGenerate = async () => {
		const trimmed = promptText.trim();
		if (!trimmed || inFlightRef.current) return;

		const autoAdvanceEnabled = autoAdvanceRef.current;

		const sourceId = resolveSourceNodeId(
			useDagStore.getState().nodes,
			useDagStore.getState().edges,
			nodeId,
			useDagStore.getState().architectSourceNodeId,
		);
		if (!sourceId) {
			const msg =
				"Aucune source détectée : reliez un reader au nœud Auto-Architect (ou placez un reader sur le canvas).";
			reportError(`Erreur : ${msg}`);
			return;
		}

		inFlightRef.current = true;
		beginLoading();
		setThinkingLog([]);
		pushThinking("Analyse de l'objectif et appel step-architect…");
		updateNodeParams(nodeId, { global_objective: trimmed, source_node_id: sourceId });
		updateNodeParams(nodeId, { auto_advance: autoAdvanceEnabled });
		appendChat({
			role: "user",
			content: trimmed,
			at: new Date().toISOString(),
		});

		try {
			discardStoreProposals();
			rejectAll();
			setArchitectSession({
				globalPlan: [],
				stepIndex: 0,
				totalSteps: 0,
				previousSteps: [],
				sourceNodeId: sourceId,
				globalObjective: trimmed,
			});

			const { firstResult, stepIndex } = await runArchitectPipeline(
				trimmed,
				sourceId,
				{
					continueUntilComplete: true,
					materialize: autoAdvanceEnabled,
					layoutStartNodeId: nodeId,
				},
			);

			const planText = (firstResult?.global_plan || []).join(" → ");
			appendChat({
				role: "assistant",
				content: planText ? `Plan : ${planText}` : "Plan généré.",
				at: new Date().toISOString(),
			});
			pushThinking(
				planText ? `Plan : ${planText}` : "Plan prêt — prévisualisation étape 1.",
			);

			if (autoAdvanceEnabled && stepIndex > 0) {
				pushThinking("Pipeline appliqué sur le canvas (auto-advance).");
				useDagStore.setState({
					inspectorOpen: false,
					importNotice: "Pipeline consolidé sur le canvas.",
					error: null,
				});
			}
		} catch (err) {
			reportError(errorMessage(err));
		} finally {
			inFlightRef.current = false;
			endLoading();
		}
	};

	const handleReject = () => {
		discardStoreProposals();
		rejectAll();
		setArchitectSession({
			globalPlan: [],
			stepIndex: 0,
			totalSteps: 0,
			previousSteps: [],
		});
		setThinkingLog([]);
		setInspectorError(null);
		pushThinking("Propositions rejetées.");
	};

	const stepNumber = Math.min(currentStepIndex + 1, totalSteps || 1);
	const canApplyPipeline = hasProposals || globalPlan.length > 0;

	return (
		<div className="auto-architect-inspector">
			<div className="auto-architect-inspector__chat">
				<ul className="auto-architect-inspector__history">
					{chatHistory.length === 0 ? (
						<li className="auto-architect-inspector__empty">
							Décrivez l&apos;objectif global du pipeline à construire.
						</li>
					) : (
						chatHistory.map((message, index) => (
							<li
								key={`${message.at}-${index}`}
								className={`auto-architect-inspector__bubble auto-architect-inspector__bubble--${message.role}`}
							>
								{message.content}
							</li>
						))
					)}
				</ul>
				<label className="auto-architect-inspector__field">
					Objectif global
					<textarea
						rows={4}
						placeholder="Reprojection EPSG:2154, filtrage des parcelles > 1000 m² et export GeoJSON"
						value={promptText}
						disabled={isGenerating}
						onChange={(e) => setPromptText(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
								e.preventDefault();
								void handleGenerate();
							}
						}}
					/>
				</label>
				<label className="auto-architect-inspector__toggle">
					<input
						type="checkbox"
						checked={autoAdvance}
						disabled={isGenerating}
						onChange={(e) => {
							const next = e.target.checked;
							setAutoAdvance(next);
							updateNodeParams(nodeId, { auto_advance: next });
						}}
					/>
					Avancement automatique (Auto-advance)
				</label>
				{!dataSourceId ? (
					<p className="auto-architect-inspector__warn">
						Aucune source détectée : reliez la sortie d’un reader (CSV, Shapefile…)
						à l’entrée de ce nœud, ou ajoutez au moins un reader sur le canvas.
					</p>
				) : (
					<p className="auto-architect-inspector__source-hint">
						Source pour le plan : <code>{dataSourceId}</code>
					</p>
				)}
				{inspectorError ? (
					<p className="auto-architect-inspector__warn" role="alert">
						{inspectorError}
					</p>
				) : null}
				<button
					type="button"
					className="auto-architect-inspector__send"
					disabled={isGenerating || !promptText.trim()}
					onClick={() => void handleGenerate()}
				>
					{isGenerating ? (
						<>
							<Loader2 size={16} className="n8n-node--direct-agent__spin" />
							Génération…
						</>
					) : (
						"Envoyer / Générer le pipeline"
					)}
				</button>
			</div>

			<button
				type="button"
				className="composer-agent-panel__accordion"
				onClick={() => setThinkingOpen((value) => !value)}
				aria-expanded={thinkingOpen}
			>
				<span>Thinking process…</span>
				<span>{thinkingOpen ? "▾" : "▸"}</span>
			</button>
			{thinkingOpen ? (
				<ul className="composer-agent-panel__thoughts">
					{thinkingLog.length ? (
						thinkingLog.map((line, index) => (
							<li key={`${index}-${line}`}>{line}</li>
						))
					) : (
						<li className="composer-agent-panel__muted">
							{isGenerating
								? "Planification step-architect…"
								: "Les logs apparaîtront après l'envoi."}
						</li>
					)}
				</ul>
			) : null}

			{globalPlan.length > 0 ? (
				<section className="step-architect__plan">
					<p className="step-architect__plan-title">
						Étape {stepNumber} / {totalSteps || globalPlan.length}
					</p>
					<ol className="step-architect__stepper auto-architect-inspector__stepper">
						{globalPlan.map((label, index) => (
							<li
								key={label}
								className={
									index < currentStepIndex
										? "is-done"
										: index === currentStepIndex
											? "is-current"
											: ""
								}
							>
								{label}
								{index < globalPlan.length - 1 ? (
									<span className="auto-architect-inspector__arrow"> ➔ </span>
								) : null}
							</li>
						))}
					</ol>
				</section>
			) : null}

			<footer className="auto-architect-inspector__footer">
				<button
					type="button"
					className="composer-agent-panel__accept"
					disabled={isGenerating || !canApplyPipeline}
					onClick={() => void handleApplyAll()}
					title="Matérialise toutes les étapes du plan"
				>
					Appliquer tout le pipeline
				</button>
				<button
					type="button"
					className="composer-agent-panel__reject"
					disabled={isGenerating}
					onClick={handleReject}
				>
					Rejeter / Annuler
				</button>
			</footer>
		</div>
	);
}
