import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/conectores",
        destination: "/settings/conectores",
        permanent: false,
      },
      {
        source: "/empresa",
        destination: "/settings/empresa",
        permanent: false,
      },
      {
        source: "/categorias",
        destination: "/settings/categorias",
        permanent: false,
      },
      {
        source: "/categorías",
        destination: "/settings/categorias",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
