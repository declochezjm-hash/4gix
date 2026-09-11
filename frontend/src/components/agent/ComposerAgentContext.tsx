import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useMemo,
} from "react";

import { useComposerAgent } from "../../hooks/useComposerAgent";
import { useDagStore } from "../../store/dagStore";

type ComposerAgentContextValue = ReturnType<typeof useComposerAgent> & {
	acceptAll: (anchorNodeId: string) => void;
	rejectAll: () => void;
	hasProposals: boolean;
};

const ComposerAgentContext = createContext<ComposerAgentContextValue | null>(
	null,
);

export function ComposerAgentProvider({ children }: { children: ReactNode }) {
	const agent = useComposerAgent();
	const applyComposerReplacement = useDagStore(
		(s) => s.applyComposerReplacement,
	);

	const hasProposals =
		agent.proposedNodes.length > 0 || agent.proposedEdges.length > 0;

	const acceptAll = useCallback(
		(anchorNodeId: string) => {
			if (!agent.proposedNodes.length && !agent.proposedEdges.length) return;
			applyComposerReplacement(
				anchorNodeId,
				agent.proposedNodes,
				agent.proposedEdges,
			);
			agent.discardProposals();
		},
		[agent, applyComposerReplacement],
	);

	const rejectAll = useCallback(() => {
		agent.discardProposals();
	}, [agent]);

	const value = useMemo(
		() => ({
			...agent,
			acceptAll,
			rejectAll,
			hasProposals,
		}),
		[agent, acceptAll, rejectAll, hasProposals],
	);

	return (
		<ComposerAgentContext.Provider value={value}>
			{children}
		</ComposerAgentContext.Provider>
	);
}

export function useComposerAgentContext(): ComposerAgentContextValue {
	const ctx = useContext(ComposerAgentContext);
	if (!ctx) {
		throw new Error(
			"useComposerAgentContext doit être utilisé dans ComposerAgentProvider",
		);
	}
	return ctx;
}
