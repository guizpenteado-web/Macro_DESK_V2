import type { NextConfig } from "next";

// Montado sob /smartmoney no Hub (unified_server.py, proxy -> :3100). basePath
// faz o Next prefixar sozinho todo asset/rota/link — sem isso, o proxy generico
// do Hub (regex simples em href="/, src="/) nao daria conta de _next/static
// nem de fetch client-side, so funciona de verdade com basePath nativo.
// O rewrite forward /smartmoney/api/* pro backend (porta 8100) — roda no
// servidor do Next, entao o browser nunca faz fetch cross-origin (sem CORS
// a resolver, e funciona igual via localhost ou via ngrok publico).
const nextConfig: NextConfig = {
  basePath: "/smartmoney",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8100/api/:path*",
      },
    ];
  },
};

export default nextConfig;
