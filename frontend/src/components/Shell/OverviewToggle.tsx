type OverviewToggleProps = {
	checked: boolean;
	onChange: (next: boolean) => void;
	labelOn: string;
	labelOff: string;
	ariaLabel: string;
};

export function OverviewToggle({
	checked,
	onChange,
	labelOn,
	labelOff,
	ariaLabel,
}: OverviewToggleProps) {
	return (
		<div
			className="overview-switch"
			onClick={(e) => e.stopPropagation()}
			onKeyDown={(e) => e.stopPropagation()}
		>
			<span
				className={
					checked ? "overview-switch__label is-on" : "overview-switch__label"
				}
			>
				{checked ? labelOn : labelOff}
			</span>
			<button
				type="button"
				role="switch"
				aria-checked={checked}
				aria-label={ariaLabel}
				className={
					checked
						? "overview-switch__control is-on"
						: "overview-switch__control"
				}
				onClick={() => onChange(!checked)}
			>
				<span className="overview-switch__track" aria-hidden />
			</button>
		</div>
	);
}
