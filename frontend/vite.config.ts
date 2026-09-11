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
			"lucide-react",
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
		headers: {
			"Cache-Control": "no-store",
		},
		proxy: {
			"/api": {
				target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
				changeOrigin: true,
				ws: true,
			},
			"/health": {
				target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
				changeOrigin: true,
			},
			"/ws": {
				target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
				ws: true,
			},
		},
	},
});
