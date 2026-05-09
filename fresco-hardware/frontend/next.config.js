/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // react-pdf requires webpack config for canvas/worker support
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
};

module.exports = nextConfig;
