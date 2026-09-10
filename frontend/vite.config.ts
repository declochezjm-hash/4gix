import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [react()],
	optimizeDeps: {
		include: [
			"@deck.gl/core",
			"@deck.gl/layers",
			"@deck.gl/mapbox",
			"maplibre-gl",
		],
	},
	css: {
		postcss: {
			plugins: [],
		},
	},
	server: {
		host: "0.0.0.0",
		port: 5173,
		strictPort: true,
		proxy: {
			"/api": {
				target: "http://4gix:8000",
				changeOrigin: true,
				ws: true,
			},
			"/health": {
				target: "http://4gix:8000",
				changeOrigin: true,
			},
			"/ws": {
				target: "ws://4gix:8000",
				ws: true,
			},
		},
	},
});
